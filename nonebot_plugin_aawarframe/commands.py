from nonebot import on_command
from nonebot.params import CommandArg

from .service.archimedea.deep import gen_deep_img
from .service.archimedea.temporal import gen_temporal_img
from .service.earth import gen_eidolon_img
from .service.arbys import gen_current_arbys_img, gen_today_arbys_img, gen_s_arbys_img
from .service.voidfissures import gen_void_fissures_img
from .service.warframe_market import render_orders_img
from .service.world_state import gen_clan_weekly_img, gen_cetus_bounty_img
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message

# 夜灵平原
eidolon = on_command("夜灵平原", aliases={"平原", "夜灵"})
@eidolon.handle()
async def cetus_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    img = await gen_eidolon_img()
    message.append(MessageSegment.image(bytes(img)))
    await eidolon.finish(message)

# ----- Archimedea -----
temporal = on_command("时光科研", aliases={"时光"})
@temporal.handle()
async def temporal_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_temporal_img())
    await temporal.finish(message)

# 深层科研
deep = on_command("深层科研", aliases={"深层"})
@deep.handle()
async def deep_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_deep_img())
    await deep.finish(message)
# ----------------------

# -------- Arbitration ---------------
current_arbys = on_command("仲裁")
@current_arbys.handle()
async def current_arbys_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_current_arbys_img())
    await current_arbys.finish(message)

today_arbys = on_command("今日仲裁")
@today_arbys.handle()
async def today_arbys_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_today_arbys_img())
    await today_arbys.finish(message)

fast_arbys = on_command("高效仲裁")
@fast_arbys.handle()
async def fast_arbys_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_s_arbys_img())
    await fast_arbys.finish(message)
# -----------------------------------

# ----- Void Fissures -----
vf = on_command("裂缝", aliases={"裂隙"})
@vf.handle()
async def vf_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_void_fissures_img(False))
    await vf.finish(message)

hard_vf = on_command("钢铁裂缝", aliases={"钢铁裂隙"})
@hard_vf.handle()
async def hard_vf_handle(event: MessageEvent):
    message = Message()
    message.append(MessageSegment.reply(event.message_id))
    message.append(await gen_void_fissures_img(True))
    await hard_vf.finish(message)

# ---- Warframe Market ----
wm = on_command("wm")
@wm.handle()
async def wm_handle(event: MessageEvent, args: Message = CommandArg()):
    message = Message()
    result = await render_orders_img(args.extract_plain_text())
    message.append(MessageSegment.image(bytes(result)))
    await wm.finish(message)

# --- 氏族奖励 ---
clan = on_command("氏族奖励")
@clan.handle()
async def clan_handle(event: MessageEvent):
    message = Message()
    result = await gen_clan_weekly_img()
    message.append(MessageSegment.text(result))
    await clan.finish(message)

# --- 赏金任务 ---
cetus = on_command("希图斯")
@cetus.handle()
async def cetus_handle():
    message = Message()
    img = await gen_cetus_bounty_img()
    message.append(MessageSegment.image(bytes(img)))
    await cetus.finish(message)
