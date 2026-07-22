import asyncio
import subprocess
import sys

from nonebot.plugin import PluginMetadata
from nonebot import get_driver
from nonebot.log import logger

from . import commands


def _run_install():
    """在子线程中执行 playwright install（同步调用，由 asyncio.to_thread 包装）"""
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--with-deps", "--only-shell"],
        capture_output=True, text=True, timeout=120,
    )


async def _init_browser():
    """安装 Chromium 并预启动浏览器"""
    logger.info("正在检查 Playwright Chromium，首次启动可能需要下载浏览器……")
    try:
        result = await asyncio.to_thread(_run_install)
        if result.returncode == 0:
            logger.info("Playwright Chromium 就绪")
        else:
            logger.warning(f"Chromium 安装可能失败: {result.stderr}")
            return
    except Exception as e:
        logger.warning(f"Chromium 安装检查失败: {e}")
        return
    # 预启动浏览器，避免首次调用时的冷启动延迟
    from .util.browser_manager import get_browser
    await get_browser()


@get_driver().on_startup
async def _init_playwright():
    """插件启动时初始化 Playwright（阻塞直到就绪，避免启动早期收到命令）"""
    await _init_browser()


__plugin_meta__ = PluginMetadata(
    name='nonebot-plugin-aawarframe',
    description='aa 的 Warframe 插件',
    usage="",
    type="application",
    extra={},
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    supported_adapters={"~onebot.v11"}
)