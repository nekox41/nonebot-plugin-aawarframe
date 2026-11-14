# Desc: 实现 commands 层的 router 功能。
# Date: 2026-11-14
# Author: Aameow

import logging

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.typing import T_State

from ..admin.control import DEFAULT_COMMANDS
from ..bootstrap import get_runtime
from ..models.common import Card
from ..models.errors import UserInputError, WikiChallengeError
from ..rendering.viewmodels import fallback_text, wiki_text
from ..services.bounties import BOUNTY_FEATURES, BOUNTY_REGIONS
from .parsing import (
    parse_bounty_index,
    parse_market_query,
    parse_riven_ranking,
    parse_riven_statistics_query,
    parse_riven_values,
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


async def dispatch(feature: str, arguments: str = "") -> Message:
    runtime = get_runtime()
    try:
        if feature in {"riven_ranking", "rolled_riven_ranking"}:
            page, sort_by = parse_riven_ranking(arguments)
            card = await runtime.rivens.ranking(
                page, sort_by, rerolled=feature == "rolled_riven_ranking"
            )
        elif feature == "riven_statistics":
            card = await runtime.rivens.statistics(parse_riven_statistics_query(arguments))
        elif feature == "riven_values":
            card = runtime.riven_values.query(*parse_riven_values(arguments))
        elif feature in BOUNTY_FEATURES:
            title = BOUNTY_REGIONS[BOUNTY_FEATURES[feature]].title
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
    async def handle(matcher: Matcher, state: T_State):
        result = await dispatch(feature, state["aawarframe_arguments"])
        await matcher.finish(result)


def setup() -> None:
    for name, aliases, feature in DEFAULT_COMMANDS:
        register(name, aliases, feature)
