"""Single-entry NoneBot2 Warframe plugin; no adapter is required at import time."""
from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_aawfcore")
__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-aawarframe",
    description="Aa 的 Warframe 助手，支持 QQ 官方与 OneBot V11",
    usage="发送 帮助 查看命令",
    type="application",
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    supported_adapters=None,
)

from .router import setup

setup()
