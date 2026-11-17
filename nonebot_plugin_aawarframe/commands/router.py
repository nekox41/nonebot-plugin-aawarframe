# Desc: 实现 commands 层的 router 功能。
# Date: 2026-11-15
# Author: Aameow

import logging

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.typing import T_State

from ..admin.control import DEFAULT_COMMANDS
from ..bootstrap import get_runtime
from ..infrastructure.riven_ocr import message_image
from ..localization.riven_attributes import attributes
from ..models.common import Card
from ..models.errors import UserInputError, WikiChallengeError
from ..rendering.viewmodels import fallback_text, wiki_text
from ..services.bounties import BOUNTY_FEATURES
from .parsing import (
    parse_bounty_index,
    parse_market_query,
    parse_relic_query,
    parse_riven_market,
    parse_riven_ranking,
    parse_riven_statistics_query,
    parse_riven_values,
    parse_trend_query,
    parse_wiki_query,
)

logger = logging.getLogger(__name__)


async def response(card: Card, runtime) -> Message:
    try:
        images = await runtime.renderer.render(card)
        return Message([MessageSegment.image(image) for image in images])
    except Exception:
        logger.exception("图片渲染失败，回退文本")
        return Message(MessageSegment.text(fallback_text(card)))


async def dispatch(
    feature: str,
    arguments: str = "",
    image: bytes | None = None,
    *,
    subscriber: tuple[str, str, str] | None = None,
) -> Message:
    runtime = get_runtime()
    try:
        if feature in {"subscribe", "list_subscriptions", "unsubscribe"}:
            text = await runtime.subscriptions.handle(feature, arguments, subscriber)
            return Message(MessageSegment.text(text))
        if feature == "riven_analysis":
            if image is None:
                raise UserInputError("请附上或引用一张紫卡图片。")
            card = await runtime.riven_analysis.query(image, arguments)
        elif feature == "help":
            if arguments.strip():
                raise UserInputError("用法：帮助")
            card = Card(title="帮助", source="命令列表", command_names=[cmd.name for cmd in runtime.control.settings.commands])
        elif feature == "riven_attributes":
            if arguments.strip():
                raise UserInputError("用法：词条")
            card = Card(title="紫卡词条", source="词条映射", attribute_rows=[(" / ".join([a["short"], *a.get("short_aliases", [])]), a["name"]) for a in attributes().values()])
        elif feature == "riven_ranking" and any(
            token != "热度" and not (token.isascii() and token.isdecimal())
            for token in arguments.split()
        ):
            card = await runtime.rivens.statistics(parse_riven_statistics_query(arguments))
        elif feature in {"riven_ranking", "rolled_riven_ranking"}:
            page, sort_by = parse_riven_ranking(arguments)
            card = await runtime.rivens.ranking(
                page, sort_by, rerolled=feature == "rolled_riven_ranking"
            )
        elif feature == "riven_values":
            card = runtime.riven_values.query(*parse_riven_values(arguments))
        elif feature in BOUNTY_FEATURES:
            title = next(cmd.name for cmd in runtime.control.settings.commands if cmd.feature == feature)
            try:
                card = await runtime.world.query(
                    feature, bounty_index=parse_bounty_index(arguments, title)
                )
            except UserInputError as exc:
                card = Card(title=title, source="命令提示", notes=[str(exc)])
        elif feature == "wiki":
            result = await runtime.wiki.search(parse_wiki_query(arguments))
            return Message(MessageSegment.text(wiki_text(result)))
        elif feature in {"arbitration", "today_arbitration", "efficient_arbitration"}:
            card = runtime.arbitration.query(feature, arguments)
        elif feature == "void_trader":
            if arguments.strip():
                raise UserInputError("用法：奸商")
            card = await runtime.trader.query()
        elif feature == "market":
            card = await runtime.market.query(parse_market_query(arguments))
        elif feature == "trend":
            card = await runtime.trend.query(parse_trend_query(arguments))
        elif feature == "parts":
            card = await runtime.relics.parts(parse_relic_query(arguments, "部件"))
        elif feature == "relic":
            card = await runtime.relics.relic(parse_relic_query(arguments, "遗物"))
        elif feature == "riven_market":
            card = await runtime.riven_market.query(parse_riven_market(arguments))
        else:
            if arguments.strip():
                raise UserInputError("此命令不接受参数。")
            card = await runtime.world.query(feature)
    except WikiChallengeError:
        return Message(MessageSegment.text("Wiki 暂时要求浏览器验证，请稍后重试。"))
    except UserInputError as exc:
        return Message(MessageSegment.text(str(exc)))
    except Exception:
        logger.exception("查询 %s 失败", feature)
        return Message(MessageSegment.text("数据源暂时不可用，请稍后重试。"))
    return await response(card, runtime)


def register(name: str, aliases: set[str], feature: str) -> None:
    async def rule(event: MessageEvent, state: T_State) -> bool:
        if "aawarframe_route" not in state:
            state["aawarframe_route"] = get_runtime().control.route(
                event.get_plaintext().lstrip(),
                get_driver().config.command_start,
                str(event.user_id),
                str(event.group_id) if hasattr(event, "group_id") else None,
            )
        route = state["aawarframe_route"]
        if route is None or route[0] != feature:
            return False
        state["aawarframe_arguments"] = route[1]
        return True

    command = on_message(rule=rule, block=True, priority=10)

    @command.handle()
    async def handle(bot: Bot, event: MessageEvent, matcher: Matcher, state: T_State):
        image = None
        if feature == "riven_analysis":
            try:
                image = await message_image(bot, event, get_runtime().http)
            except UserInputError as exc:
                await matcher.finish(str(exc))
            except Exception:
                logger.exception("下载紫卡图片失败")
                await matcher.finish("无法下载图片，请重新上传。")
        subscriber = (
            (str(bot.self_id), str(event.group_id), str(event.user_id))
            if isinstance(event, GroupMessageEvent)
            else None
        )
        result = await dispatch(
            feature, state["aawarframe_arguments"], image, subscriber=subscriber
        )
        await matcher.finish(result)


def setup() -> None:
    for name, aliases, feature in DEFAULT_COMMANDS:
        register(name, aliases, feature)
