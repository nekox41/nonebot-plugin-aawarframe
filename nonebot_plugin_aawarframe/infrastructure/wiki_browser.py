# 作用：实现 infrastructure 层的 wiki_browser 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from ..models.errors import WikiChallengeError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from playwright.async_api import Page


def _wiki_page() -> AbstractAsyncContextManager["Page"]:
    # 借用 htmlrender 的浏览器，专用页面由本客户端持有至插件关闭。
    from nonebot_plugin_htmlrender import get_default_application

    return get_default_application().extensions.playwright.page(locale="zh-CN")


class WikiBrowserClient:
    def __init__(
        self,
        timeout: float = 30,
        *,
        page_factory: Callable[[], AbstractAsyncContextManager["Page"]] | None = None,
    ):
        self.timeout = timeout
        self.page_factory = page_factory or _wiki_page
        self.semaphore = asyncio.Semaphore(1)
        self._page: Page | None = None
        self._page_context: AbstractAsyncContextManager[Page] | None = None

    async def _release_page(self) -> None:
        context = self._page_context
        self._page = None
        self._page_context = None
        if context is not None:
            await context.__aexit__(None, None, None)

    async def _get_page(self) -> "Page":
        if self._page is not None and not self._page.is_closed():
            return self._page
        await self._release_page()
        context = self.page_factory()
        page = await context.__aenter__()
        self._page_context = context
        self._page = page
        return page

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        async with self.semaphore:
            challenged = False
            last_status: int | None = None
            page = None

            def track_response(response):
                nonlocal challenged, last_status
                if response.request.is_navigation_request() and response.frame == page.main_frame:
                    last_status = response.status
                    mitigated = response.headers.get("cf-mitigated") == "challenge"
                    challenged = challenged or mitigated
                    logger.info("Wiki 页面导航：HTTP %s，验证标记=%s", last_status, mitigated)

            try:
                async with asyncio.timeout(self.timeout):
                    page = await self._get_page()
                    page.on("response", track_response)
                    await page.set_extra_http_headers(headers or {})
                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=self.timeout * 1000
                    )
                    if response is None:
                        raise RuntimeError("Wiki 页面访问未返回响应")
                    if not response.ok and not challenged:
                        raise RuntimeError(f"Wiki 页面访问失败，HTTP {response.status}")
                    # 首次导航可能仍是中间页，等待浏览器后续导航产生真正的 JSON。
                    # 不刷新、不点击验证控件，也不额外重试请求。
                    await page.wait_for_function(
                        """() => {
                            const element = document.querySelector('body pre') || document.body;
                            if (!element) return false;
                            try {
                                JSON.parse(element.innerText.replace(/^\ufeff/, '').trim());
                                return true;
                            } catch { return false; }
                        }""",
                        timeout=self.timeout * 1000,
                    )
                    pre = page.locator("body pre").first
                    text = (
                        await pre.inner_text()
                        if await pre.count()
                        else await page.locator("body").inner_text()
                    )
                    result = json.loads(text.lstrip("\ufeff").strip())
                    if last_status is not None and last_status >= 400:
                        raise RuntimeError(f"Wiki 页面访问失败，HTTP {last_status}")
                    logger.info("Wiki 页面 JSON 读取完成：HTTP %s", last_status)
                    return result
            except (TimeoutError, PlaywrightTimeoutError) as exc:
                if challenged:
                    logger.warning(
                        "Wiki 等待 %.0f 秒后仍未返回 JSON：HTTP %s，曾出现验证页",
                        self.timeout,
                        last_status,
                    )
                    raise WikiChallengeError("Wiki 浏览器验证未在等待时限内完成") from exc
                raise RuntimeError("Wiki 页面未在等待时限内展示 JSON") from exc
            finally:
                if page is not None:
                    page.remove_listener("response", track_response)

    async def close(self) -> None:
        async with self.semaphore:
            await self._release_page()
