# 作用：初始化 nonebot_plugin_aawarframe 模块。
# 编写日期：2026-11-07
# 作者：Aameow

from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

require("nonebot_plugin_htmlrender")

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-aawarframe",
    description="国际服 Warframe 世界状态与交易市场查询",
    usage="发送 help 或 wf help 查看命令。",
    type="application",
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

from .bootstrap import setup as setup_runtime  # noqa: E402
from .commands.router import setup as setup_commands  # noqa: E402

setup_runtime()
setup_commands()
