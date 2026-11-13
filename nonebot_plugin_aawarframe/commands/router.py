# 作用：实现 commands 层的 router 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import logging

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..bootstrap import get_runtime
from ..models.common import Card
from ..models.errors import UserInputError, WikiChallengeError
from ..rendering.viewmodels import fallback_text, wiki_text
from ..services.bounties import BOUNTY_FEATURES, BOUNTY_REGIONS
from ..services.help import help_card
from .parsing import (
    parse_bounty_index,
    parse_market_query,
    parse_riven_ranking,
    parse_riven_statistics_query,
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
        if feature == "help":
            card = help_card(arguments)
        elif feature == "wf":
            parts = arguments.strip().split(maxsplit=1)
            if parts and parts[0] not in {"help", "帮助"}:
                raise UserInputError("用法：wf help 2")
            card = help_card(parts[1] if len(parts) > 1 else "")
        elif feature in {"riven_ranking", "rolled_riven_ranking"}:
            page, sort_by = parse_riven_ranking(arguments)
            card = await runtime.rivens.ranking(
                page, sort_by, rerolled=feature == "rolled_riven_ranking"
            )
        elif feature == "riven_statistics":
            card = await runtime.rivens.statistics(parse_riven_statistics_query(arguments))
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
        elif feature == "market":
            card = await runtime.market.query(parse_market_query(arguments))
        else:
            if arguments.strip():
                raise UserInputError("此命令不接受参数，请发送 help 查看用法。")
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
    command = on_command(name, aliases=aliases, block=True, priority=10)

    @command.handle()
    async def handle(matcher: Matcher, args: Message = CommandArg()):
        result = await dispatch(feature, args.extract_plain_text())
        await matcher.finish(result)


def setup() -> None:
    for name, aliases, feature in [
        ("help", {"wf帮助"}, "help"),
        ("wf", set(), "wf"),
        ("平原", set(), "plains"),
        ("时光科研", {"时光"}, "temporal"),
        ("深层科研", {"深层"}, "deep"),
        ("裂缝", {"裂隙"}, "fissures"),
        ("钢铁裂缝", {"钢铁裂隙"}, "steel_fissures"),
        ("九重天", {"九重天裂缝"}, "railjack_fissures"),
        ("氏族", {"氏族奖励"}, "clan"),
        ("午夜电波", {"电波"}, "nightwave"),
        ("日历", set(), "calendar"),
        ("钢精", set(), "steel_path"),
        ("回廊", set(), "circuit"),
        ("灵化", set(), "incarnons"),
        ("赏金", set(), "bounty_summary"),
        ("地球赏金", {"地球"}, "bounties"),
        ("金星赏金", {"金星"}, "venus_bounties"),
        ("火卫二赏金", {"火卫二"}, "deimos_bounties"),
        ("圣所赏金", set(), "sanctum_bounties"),
        ("扎里曼赏金", set(), "zariman_bounties"),
        ("1999赏金", set(), "hex_bounties"),
        ("仲裁", set(), "arbitration"),
        ("今日仲裁", set(), "today_arbitration"),
        ("高效仲裁", set(), "efficient_arbitration"),
        ("wm", set(), "market"),
        ("wk", {"wiki"}, "wiki"),
        ("紫卡排行", set(), "riven_ranking"),
        ("已洗紫卡排行", set(), "rolled_riven_ranking"),
        ("紫卡统计", set(), "riven_statistics"),
    ]:
        register(name, aliases, feature)
