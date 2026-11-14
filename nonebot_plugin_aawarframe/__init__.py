# Desc: 声明插件信息并注册查询功能。
# Date: 2026-11-14
# Author: Aameow

from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

require("nonebot_plugin_htmlrender")

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-aawarframe",
    description="国际服 Warframe 世界状态与交易市场查询",
    usage="命令与配置见 README。",
    type="application",
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

from .bootstrap import setup as setup_runtime  # noqa: E402
from .commands.router import setup as setup_commands  # noqa: E402

setup_runtime()
setup_commands()
