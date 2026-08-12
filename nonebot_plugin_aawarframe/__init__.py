from nonebot import require
require("nonebot_plugin_htmlrender")
from nonebot.plugin import PluginMetadata
from . import commands


__plugin_meta__ = PluginMetadata(
    name='nonebot-plugin-aawarframe',
    description='aa 的 Warframe 插件',
    usage="",
    type="application",
    extra={},
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    supported_adapters={"~onebot.v11"}
)