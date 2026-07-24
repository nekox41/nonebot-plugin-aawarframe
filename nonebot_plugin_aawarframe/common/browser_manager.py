# Playwright 浏览器单例管理
# 描述：管理无头 Chromium 的生命周期，提供 html_to_pic 渲染接口
# 作者：aa
# 2026年7月22日

from typing import Optional

from nonebot.log import logger
from playwright.async_api import Browser, Page, Playwright, async_playwright

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None


async def _launch_browser() -> Browser:
    """启动无头 Chromium 浏览器实例"""
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)
    logger.info("Playwright 无头 Chromium 已启动")
    return _browser


async def get_browser() -> Browser:
    """获取浏览器单例，首次调用时自动启动"""
    global _browser
    if _browser is None or not _browser.is_connected():
        _browser = await _launch_browser()
    return _browser


async def html_to_pic(html: str) -> bytes:
    """
    将 HTML 字符串渲染为 PNG 图片字节

    :param html: 完整的 HTML 字符串
    :return: PNG 图片二进制数据
    """
    browser = await get_browser()
    page: Page = await browser.new_page()
    try:
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        body = page.locator("body")
        return await body.screenshot(type="png")
    finally:
        await page.close()


async def shutdown_browser():
    """关闭浏览器和 Playwright，用于插件卸载时清理"""
    global _browser, _playwright
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright 浏览器已关闭")
