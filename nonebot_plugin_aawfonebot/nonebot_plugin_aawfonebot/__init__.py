"""AAWarframe 的 OneBot V11 入口，兼容现有 OneBot 用户。"""

from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="aawfonebot",
    description="AAWarframe · OneBot V11",
    usage="命令详见 nonebot-plugin-aawarframe README",
    type="application",
    supported_adapters={"~onebot.v11"},
)

require("nonebot_plugin_aawarframe")
