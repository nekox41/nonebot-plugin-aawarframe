"""Aa 的 Warframe 助手：NoneBot2 插件入口。"""

from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

require("nonebot_plugin_htmlrender")

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-aawarframe",
    description="Aa 的 Warframe 助手，支持 QQ 官方与 OneBot V11",
    usage="发送 帮助 查看命令",
    type="application",
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    config=Config,
    supported_adapters=None,
)

from .bootstrap import setup as setup_runtime  # noqa: E402

setup_runtime()

from .router import setup  # noqa: E402

setup()
