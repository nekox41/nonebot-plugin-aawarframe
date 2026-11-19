"""AAWarframe 的 QQ 官方机器人入口，只安装 QQ 官方适配器。"""

from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="aawfqq",
    description="AAWarframe · QQ 官方机器人",
    usage="命令详见 nonebot-plugin-aawarframe README",
    type="application",
    supported_adapters={"~qq"},
)

require("nonebot_plugin_aawarframe")
