import logging

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..bootstrap import get_runtime
from ..models.common import Card
from ..models.errors import UserInputError
from ..rendering.viewmodels import fallback_text
from ..services.help import help_card
from .parsing import (parse_market_query, parse_riven_ranking,
                      parse_riven_statistics_query)

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
            if arguments.strip():
                raise UserInputError("help 命令不接受参数。")
            card = help_card()
        elif feature == "wf":
            if arguments.strip() not in {"", "help", "帮助"}:
                raise UserInputError("用法：wf help")
            card = help_card()
        elif feature in {"riven_ranking", "rolled_riven_ranking"}:
            page, sort_by = parse_riven_ranking(arguments)
            card = await runtime.rivens.ranking(
                page, sort_by, rerolled=feature == "rolled_riven_ranking"
            )
        elif feature == "riven_statistics":
            card = await runtime.rivens.statistics(parse_riven_statistics_query(arguments))
        elif feature == "market":
            card = await runtime.market.query(parse_market_query(arguments))
        else:
            if arguments.strip():
                raise UserInputError("此命令不接受参数，请发送 help 查看用法。")
            card = await runtime.world.query(feature)
    except UserInputError as exc:
        return Message(MessageSegment.text(str(exc)))
    except Exception:
        logger.exception("查询 %s 失败", feature)
        return Message(MessageSegment.text("数据源暂时不可用，请稍后重试。"))
    return await response(card, runtime)


def register(name: str, aliases: set[str], feature: str) -> None:
    command = on_command(name, aliases=aliases, block=True, priority=10)

    @command.handle()
    async def handle(matcher: Matcher, event: MessageEvent, args: Message = CommandArg()):
        result = await dispatch(feature, args.extract_plain_text())
        await matcher.finish(MessageSegment.reply(event.message_id) + result)


def setup() -> None:
    for name, aliases, feature in [
        ("help", {"wf帮助"}, "help"),
        ("wf", set(), "wf"),
        ("夜灵", set(), "cetus"),
        ("平原", set(), "plains"),
        ("时光科研", {"时光"}, "temporal"),
        ("深层科研", {"深层"}, "deep"),
        ("裂缝", {"裂隙"}, "fissures"),
        ("钢铁裂缝", {"钢铁裂隙"}, "steel_fissures"),
        ("九重天", {"九重天裂缝"}, "railjack_fissures"),
        ("氏族奖励", set(), "clan"),
        ("希图斯", set(), "bounties"),
        ("仲裁", set(), "arbitration"),
        ("今日仲裁", set(), "today_arbitration"),
        ("高效仲裁", set(), "efficient_arbitration"),
        ("wm", set(), "market"),
        ("紫卡排行", set(), "riven_ranking"),
        ("已洗紫卡排行", set(), "rolled_riven_ranking"),
        ("紫卡统计", set(), "riven_statistics"),
    ]:
        register(name, aliases, feature)
