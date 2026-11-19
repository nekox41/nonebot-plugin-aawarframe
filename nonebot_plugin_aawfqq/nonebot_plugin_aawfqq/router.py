"""QQ 官方消息事件和收发。所有业务判断、渲染和订阅存储在 core。"""

import asyncio
import base64
import logging

from nonebot import get_bots, get_driver, on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.typing import T_State

from nonebot_plugin_aawfcore.client import CoreClient, decode_image
from .media import download_image

logger = logging.getLogger(__name__)
client = CoreClient()
task: asyncio.Task | None = None


def session(bot: Bot, event: Event):
    if group := getattr(event, "group_openid", None):
        return str(bot.self_id), "qq-group:" + str(group), event.get_user_id()
    if getattr(event, "channel_id", None) and getattr(event, "guild_id", None):
        return (
            str(bot.self_id), "qq-channel:" + str(event.channel_id), event.get_user_id()
        )
    return str(bot.self_id), None, event.get_user_id()


async def event_image(event: Event) -> bytes:
    message = event.get_message()
    images = [segment for segment in message if segment.type == "image"]
    if not images:
        quoted = getattr(event, "get_reply_message", lambda: None)()
        images = [segment for segment in quoted if segment.type == "image"] if quoted else []
    if len(images) != 1:
        raise ValueError("请附上或引用一张紫卡图片。")
    url = images[0].data.get("url")
    if not isinstance(url, str):
        raise ValueError("图片地址不可用，请重新发送。")
    content = await download_image(url)
    if not content:
        raise ValueError("无法下载紫卡图片，请重新发送。")
    return content


def pages(segments: list[dict]) -> list[Message]:
    """QQ 官方一个发送请求只带一张媒体；多张图片按顺序拆分。"""
    result, message, media = [], Message(), False
    for part in segments:
        kind = part["type"]
        if kind == "image":
            if media:
                result.append(message)
                message, media = Message(), False
            message += MessageSegment.file_image(decode_image(part))
            media = True
        elif kind == "text":
            message += MessageSegment.text(part["text"])
        elif kind == "at":
            message += MessageSegment.mention_user(part["user_id"])
        elif kind == "reply":
            message += MessageSegment.reference(part["message_id"])
        else:
            raise ValueError(f"不支持的 QQ 消息段：{kind}")
    if message:
        result.append(message)
    return result


async def accept(bot: Bot, event: Event, matcher: Matcher, state: T_State):
    bot_id, group_id, user_id = session(bot, event)
    image_base64 = None
    if state["aawf_feature"] == "riven_analysis":
        try:
            image_base64 = base64.b64encode(await event_image(event)).decode("ascii")
        except Exception as exc:
            await matcher.finish(MessageSegment.text(str(exc)))
            return
    try:
        result = await client.query(
            feature=state["aawf_feature"], arguments=state["aawf_arguments"],
            bot_id=bot_id, group_id=group_id, user_id=user_id,
            image_base64=image_base64,
        )
        for page in pages(result["segments"]):
            await bot.send(event, page)
    except Exception:
        logger.exception("QQ 官方回复失败")
        try:
            await bot.send(event, MessageSegment.text("查询暂不可用，请稍后重试。"))
        except Exception:
            logger.warning("QQ 官方文本回退失败，可能超出回复窗口", exc_info=True)
    await matcher.finish()


async def deliver(bot: Bot, delivery: dict):
    contents = pages(delivery["segments"])
    target = delivery["group_id"]
    if target.startswith("qq-group:"):
        for page in contents:
            await bot.send_to_group(group_openid=target[len("qq-group:"):], message=page)
    elif target.startswith("qq-channel:"):
        for page in contents:
            await bot.send_to_channel(channel_id=target[len("qq-channel:"):], message=page)
    else:
        raise ValueError("不是 QQ 官方会话")


async def notifications():
    while True:
        try:
            bots = {
                str(bot.self_id): bot for bot in get_bots().values()
                if getattr(bot, "type", None) == "QQ"
            }
            if bots:
                for item in await client.claim(list(bots), protocol="qq"):
                    try:
                        await deliver(bots[item["bot_id"]], item)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("QQ 官方订阅推送失败", exc_info=True)
                        await client.ack(item["id"], ok=False, error=type(exc).__name__)
                    else:
                        await client.ack(item["id"], ok=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("QQ 官方订阅推送轮询异常")
        await asyncio.sleep(5)


def setup():
    async def rule(bot: Bot, event: Event, state: T_State) -> bool:
        if getattr(bot, "type", None) != "QQ":
            return False
        _, group_id, user_id = session(bot, event)
        try:
            route = await client.route(
                text=event.get_plaintext(), starts=list(get_driver().config.command_start),
                user_id=user_id, group_id=group_id,
            )
        except Exception:
            logger.exception("核心 API 命令匹配失败")
            return False
        if not route["matched"]:
            return False
        state["aawf_feature"] = route["feature"]
        state["aawf_arguments"] = route["arguments"]
        return True

    matcher = on_message(rule=rule, block=True, priority=10)
    matcher.handle()(accept)

    driver = get_driver()

    @driver.on_startup
    async def startup():
        global task
        task = asyncio.create_task(notifications())

    @driver.on_shutdown
    async def shutdown():
        global task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            task = None
        await client.close()
