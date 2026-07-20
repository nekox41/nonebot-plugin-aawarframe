from nonebot import require

require("nonebot_plugin_htmlkit")

from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
from .data_sources import get_source
from .renderers import renderer


__plugin_meta__ = PluginMetadata(
    name='nonebot-plugin-aawarframe',
    description='aa 的 Warframe 插件',
    usage="",
    type="application",
    extra={},
    homepage="https://github.com/nekox41/nonebot-plugin-aawarframe",
    supported_adapters={"~onebot.v11"}
)

# -----------------------

temporal_cmd = on_command("时光科研")

@temporal_cmd.handle()
async def temporal_cmd_handle():
    temporal_source = get_source("temporal_archimedea")
    data = await temporal_source.fetch()
    img = await renderer.render(data, "archimedea","archimedea.html", "temporal.img")
    await temporal_cmd.finish(MessageSegment.image(img))

deep_cmd = on_command("深层科研")
@deep_cmd.handle()
async def deep_cmd_handle():
    deep_source = get_source("deep_archimedea")
    data = await deep_source.fetch()
    img = await renderer.render(data, "archimedea", "archimedea.html", "deep.img")
    await deep_cmd.finish(MessageSegment.image(img))