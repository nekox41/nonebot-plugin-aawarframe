"""Unified matcher and in-process Warframe query dispatch.

The NoneBot Bot/Event abstractions handle input. Platform-specific media and
unprompted notifications are kept as small lazy-loaded boundaries.
"""
import asyncio
import logging
from datetime import datetime, timezone

from nonebot import get_bots, get_driver, on_message
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.typing import T_State

from nonebot_plugin_aawfcore.bootstrap import get_runtime
from nonebot_plugin_aawfcore.commands.router import dispatch
from nonebot_plugin_aawfcore.protocols.message import Message, MessageSegment

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None

def protocol(bot: Bot) -> str | None:
    name = getattr(bot, "type", None)
    return "qq" if name == "QQ" else "onebot" if name == "OneBot V11" else None

def session(bot: Bot, event: Event):
    if protocol(bot) == "qq":
        group = getattr(event, "group_openid", None)
        if group:
            return str(bot.self_id), "qq-group:" + str(group), event.get_user_id()
        channel = getattr(event, "channel_id", None)
        if channel and getattr(event, "guild_id", None):
            return str(bot.self_id), "qq-channel:" + str(channel), event.get_user_id()
        return str(bot.self_id), None, event.get_user_id()
    group = getattr(event, "group_id", None)
    return str(bot.self_id), str(group) if group is not None else None, event.get_user_id()

async def read_image(bot: Bot, event: Event) -> bytes:
    if protocol(bot) == "onebot":
        from .media_onebot import message_image
        return await message_image(bot, event)
    if protocol(bot) == "qq":
        from .media_qq import download_image
        message = event.get_message()
        images = [item for item in message if item.type == "image"]
        if not images:
            quoted = getattr(event, "get_reply_message", lambda: None)()
            if quoted:
                images = [item for item in quoted if item.type == "image"]
        if len(images) != 1:
            raise ValueError("请附上或引用一张紫卡图片。")
        url = images[0].data.get("url")
        data = await download_image(url) if isinstance(url, str) else None
        if data is None:
            raise ValueError("无法下载紫卡图片，请重新发送。")
        return data
    raise ValueError("当前适配器尚不支持图片 OCR。")

def convert(message: Message, kind: str):
    if kind == "onebot":
        from nonebot.adapters.onebot.v11 import Message as NativeMessage
        from nonebot.adapters.onebot.v11 import MessageSegment as Segment
        result = NativeMessage()
        for item in message:
            if item.type == "text":
                result += Segment.text(item.data["text"])
            elif item.type == "image":
                result += Segment.image(item.data["file"])
            elif item.type == "at":
                result += Segment.at(item.data["qq"])
            elif item.type == "reply":
                result += Segment.reply(int(item.data["id"]))
        return [result]
    if kind == "qq":
        from nonebot.adapters.qq import Message as NativeMessage
        from nonebot.adapters.qq import MessageSegment as Segment
        pages, current, has_media = [], NativeMessage(), False
        for item in message:
            if item.type == "image":
                if has_media:
                    pages.append(current)
                    current, has_media = NativeMessage(), False
                image = item.data["file"]
                current += Segment.file_image(image) if isinstance(image, bytes) else Segment.image(image)
                has_media = True
            elif item.type == "text":
                current += Segment.text(item.data["text"])
            elif item.type == "at":
                current += Segment.mention_user(str(item.data["qq"]))
            elif item.type == "reply":
                current += Segment.reference(str(item.data["id"]))
        if current:
            pages.append(current)
        return pages
    raise ValueError("不支持的适配器")

async def reply(bot: Bot, event: Event, message: Message):
    for page in convert(message, protocol(bot)):
        await bot.send(event, page)

async def deliver(bot: Bot, item):
    result = await get_runtime().subscriptions.prepare_delivery(item, datetime.now(timezone.utc))
    pages = convert(result, protocol(bot))
    if protocol(bot) == "onebot":
        for page in pages:
            await bot.send_group_msg(group_id=int(item.group_id), message=page)
    else:
        target = item.group_id
        if target.startswith("qq-group:"):
            for page in pages:
                await bot.send_to_group(group_openid=target[len("qq-group:"):], message=page)
        elif target.startswith("qq-channel:"):
            for page in pages:
                await bot.send_to_channel(channel_id=target[len("qq-channel:"):], message=page)
        else:
            raise ValueError("不支持的 QQ 订阅目标")

async def notifications():
    while True:
        try:
            bots = {(protocol(bot), str(bot.self_id)): bot
                    for bot in get_bots().values() if protocol(bot) is not None}
            store = get_runtime().subscriptions.store
            for kind in ("qq", "onebot"):
                ids = {bot_id for (adapter, bot_id) in bots if adapter == kind}
                for item in store.claim_due(datetime.now(timezone.utc), ids, protocol=kind):
                    try:
                        await deliver(bots[(kind, item.bot_id)], item)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.exception("订阅通知发送失败")
                        store.mark_failed(item.id, item.attempts + 1,
                                          datetime.now(timezone.utc), type(exc).__name__)
                    else:
                        store.mark_sent(item.id, datetime.now(timezone.utc))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("订阅发送任务异常")
        await asyncio.sleep(5)

def setup():
    async def rule(bot: Bot, event: Event, state: T_State) -> bool:
        if protocol(bot) is None:
            return False
        bot_id, group_id, user_id = session(bot, event)
        try:
            route = get_runtime().control.route(
                event.get_plaintext().lstrip(),
                set(get_driver().config.command_start),
                user_id, group_id,
            )
        except Exception:
            logger.exception("Warframe 命令解析失败")
            return False
        if route is None:
            return False
        state["aawf_route"] = route
        return True

    matcher = on_message(rule=rule, block=True, priority=10)

    @matcher.handle()
    async def handle(bot: Bot, event: Event, state: T_State):
        feature, arguments = state["aawf_route"]
        bot_id, group_id, user_id = session(bot, event)
        try:
            image = None
            if feature == "riven_analysis":
                ocr = get_runtime().ocr
                async with ocr.admission():
                    async with asyncio.timeout(25):
                        async with ocr.download_slots:
                            image = await read_image(bot, event)
                    message = await dispatch(
                        feature, arguments, image,
                        subscriber=(bot_id, group_id, user_id) if group_id else None,
                    )
            else:
                message = await dispatch(
                    feature, arguments,
                    subscriber=(bot_id, group_id, user_id) if group_id else None,
                )
            await reply(bot, event, message)
        except ValueError as exc:
            await bot.send(event, str(exc))
        except Exception:
            logger.exception("Warframe 命令执行或发送失败")
            try:
                await bot.send(event, "查询暂不可用，请稍后重试。")
            except Exception:
                logger.warning("文本回退失败", exc_info=True)
        await matcher.finish()

    driver = get_driver()

    @driver.on_startup
    async def startup():
        global _task
        if _task is None or _task.done():
            _task = asyncio.create_task(notifications(), name="aawf-delivery")

    @driver.on_shutdown
    async def shutdown():
        global _task
        if _task is not None:
            _task.cancel()
            await asyncio.gather(_task, return_exceptions=True)
            _task = None
