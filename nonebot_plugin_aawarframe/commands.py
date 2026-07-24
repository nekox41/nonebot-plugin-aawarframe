from nonebot import on_command
from .service.archimedea.deep import gen_deep_img
from .service.archimedea.temporal import gen_temporal_img
from .service.earth import gen_eidolon_img
from .service.arbys import gen_current_arbys_img, gen_today_arbys_img, gen_s_arbys_img
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

current_arbys = on_command("仲裁")
@current_arbys.handle()
async def current_arbys_handle():
    await current_arbys.finish(await gen_current_arbys_img())

today_arbys = on_command("今日仲裁")
@today_arbys.handle()
async def today_arbys_handle():
    await today_arbys.finish(await gen_today_arbys_img())

fast_arbys = on_command("高效仲裁")
@fast_arbys.handle()
async def fast_arbys_handle():
    await fast_arbys.finish(await gen_s_arbys_img())