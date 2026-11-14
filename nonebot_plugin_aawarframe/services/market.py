# 作用：匹配可交易物品与等级，整理 Top 买卖订单和物品展示信息。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
import re
from html import unescape

from ..localization.resolver import ItemResolver
from ..models.common import Card, DataStatus
from ..models.errors import UserInputError
from ..models.market import MarketBoard, MarketQuery, Order
from ..providers.market import MarketProvider


class MarketService:
    def __init__(self, provider: MarketProvider):
        self.provider = provider

    async def query(self, query: MarketQuery) -> Card:
        catalog = await self.provider.catalog()
        resolver = await asyncio.to_thread(ItemResolver, catalog.data)
        result = resolver.resolve_result(query.name)
        if result.status == "ambiguous":
            raise UserInputError(
                "名称不够明确，请使用完整名称："
                + "、".join(
                    f"{e.name()}（{e.identifiers.get('market.slug', e.id)}）"
                    for e in result.candidates
                )
            )
        slug = result.resource.identifiers.get("market.slug") if result.resource else None
        if slug is None:
            raise UserInputError("未找到匹配物品，请使用更完整的中文或英文名称。")
        details = await self.provider.item(slug)
        item = details.data
        if not item.tradable:
            raise UserInputError("此物品不可交易。")
        if query.max_rank and item.max_rank is None:
            raise UserInputError("此物品不存在等级。")
        rank = item.max_rank if query.max_rank else query.rank
        if rank is not None and (item.max_rank is None or rank > item.max_rank):
            raise UserInputError("等级超出此物品范围。")
        if rank is None and item.max_rank is not None:
            rank = 0
        if query.subtype is not None and query.subtype not in item.subtypes:
            raise UserInputError("不支持此子类型，可用值：" + "、".join(item.subtypes))
        effective = query.model_copy(update={"rank": rank})
        snapshot = await self.provider.orders(slug, effective)
        board = MarketBoard(
            name=item.name(),
            rank=rank,
            max_rank=item.max_rank,
            subtype=query.subtype,
        )
        localized = item.i18n.get("zh-hans") or item.i18n.get("en")
        board.description = plain_description(localized.description if localized else "")
        board.image = await self.provider.icon(item)
        # Top 接口已按交易规则排序；本地只校验条件和截取条数。
        for side, limit in [("sell", 5), ("buy", 3)]:
            orders = [
                o
                for o in getattr(snapshot.data, side)
                if o.type == side and self.visible(o, effective)
            ]
            setattr(board, side, orders[:limit])
        return Card(
            title=item.name(),
            market_board=board,
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
            stale=snapshot.stale or details.stale or catalog.stale,
            status=DataStatus.OK if board.sell or board.buy else DataStatus.EMPTY,
        )

    @staticmethod
    def visible(order: Order, query: MarketQuery) -> bool:
        return bool(
            order.visible
            and order.user
            and order.user.status in {"online", "ingame"}
            and order.quantity >= order.per_trade
            and (
                order.user.platform == query.platform or (query.crossplay and order.user.crossplay)
            )
            and (query.rank is None or order.rank == query.rank)
            and (query.subtype is None or order.subtype == query.subtype)
        )


def plain_description(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>|</p>", "\n", value)
    value = unescape(re.sub(r"<[^>]+>", "", value))
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())
