"""AAWarframe OneBot V11 前端：仅负责输入事件、图片与平台输出。"""

from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="aawfonebot",
    description="AAWarframe OneBot V11 协议插件",
    usage="使用帮助命令查看 Warframe 机器人支持的查询功能",
    type="application",
    supported_adapters={"~onebot.v11"},
)

require("nonebot_plugin_aawfcore")

from .router import setup  # noqa: E402

setup()
