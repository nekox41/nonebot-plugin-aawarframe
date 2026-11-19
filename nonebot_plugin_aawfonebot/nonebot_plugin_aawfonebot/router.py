"""OneBot V11 仅收发消息，通过共享核心 HTTP API 执行业务。"""

import asyncio
import base64
import logging

from nonebot import get_bots, get_driver, on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.typing import T_State

from nonebot_plugin_aawfcore.client import CoreClient, decode_image
from .media import message_image

logger = logging.getLogger(__name__)
client = CoreClient()
task: asyncio.Task | None = None


def session(bot: Bot, event: Event):
    user_id = str(getattr(event, "user_id", event.get_user_id()))
    group = getattr(event, "group_id", None)
    return str(bot.self_id), str(group) if group is not None else None, user_id


def outbound(segments: list[dict]) -> Message:
    message = Message()
    for part in segments:
        kind = part["type"]
        if kind == "text":
            message += MessageSegment.text(part["text"])
        elif kind == "image":
            message += MessageSegment.image(decode_image(part))
        elif kind == "at":
            message += MessageSegment.at(part["user_id"])
        elif kind == "reply":
            message += MessageSegment.reply(int(part["message_id"]))
        else:
            raise ValueError(f"不支持的 OneBot 消息段：{kind}")
    return message


async def accept(bot: Bot, event: Event, matcher: Matcher, state: T_State):
    bot_id, group_id, user_id = session(bot, event)
    image_base64 = None
    if state["aawf_feature"] == "riven_analysis":
        try:
            data = await message_image(bot, event)
            image_base64 = base64.b64encode(data).decode("ascii")
        except Exception as exc:
            await matcher.finish(MessageSegment.text(str(exc)))
            return
    try:
        result = await client.query(
            feature=state["aawf_feature"], arguments=state["aawf_arguments"],
            bot_id=bot_id, group_id=group_id, user_id=user_id,
            image_base64=image_base64,
        )
        await matcher.finish(outbound(result["segments"]))
    except Exception:
        logger.exception("OneBot 核心 API 查询失败")
        await matcher.finish("查询暂不可用，请稍后重试。")


async def notifications():
    while True:
        try:
            bots = {
                str(bot.self_id): bot for bot in get_bots().values()
                if getattr(bot, "type", None) == "OneBot V11"
            }
            if bots:
                for item in await client.claim(list(bots), protocol="onebot"):
                    try:
                        await bots[item["bot_id"]].send_group_msg(
                            group_id=int(item["group_id"]),
                            message=outbound(item["segments"]),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("OneBot 订阅通知发送失败", exc_info=True)
                        await client.ack(item["id"], ok=False, error=type(exc).__name__)
                    else:
                        await client.ack(item["id"], ok=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("OneBot 订阅通知轮询异常")
        await asyncio.sleep(5)


def setup():
    async def rule(bot: Bot, event: Event, state: T_State) -> bool:
        if getattr(bot, "type", None) != "OneBot V11":
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
