from nonebot import on_command
from .service.archimedea.deep import gen_deep_img
from .service.archimedea.temporal import gen_temporal_img
from .service.cycle.eidolon import gen_eidolon_img

# 夜灵平原
cetus = on_command("夜灵平原")

@cetus.handle()
async def cetus_handle():
    await cetus.finish(await gen_eidolon_img())

# 时光科研
temporal = on_command("时光科研")

@temporal.handle()
async def temporal_handle():
    await temporal.finish(await gen_temporal_img())

# 深层科研
deep = on_command("深层科研")

@deep.handle()
async def deep_handle():
    await deep.finish(await gen_deep_img())