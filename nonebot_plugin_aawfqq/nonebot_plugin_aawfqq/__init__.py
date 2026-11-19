"""AAWarframe QQ 官方插件：只负责事件、媒体与消息发送。"""

from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="aawfqq",
    description="AAWarframe 官方 QQ 协议插件",
    usage="使用帮助命令查看 Warframe 机器人支持的查询功能",
    type="application",
    supported_adapters={"~qq"},
)

require("nonebot_plugin_aawfcore")

from .router import setup  # noqa: E402

setup()
