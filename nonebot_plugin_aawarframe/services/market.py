from ..localization.resolver import ItemResolver
from ..models.common import Card, DataStatus, Section
from ..models.errors import UserInputError
from ..models.market import MarketQuery, Order
from ..providers.market import MarketProvider


class MarketService:
    def __init__(self, provider: MarketProvider):
        self.provider = provider

    async def query(self, query: MarketQuery) -> Card:
        catalog = await self.provider.catalog()
        slug = ItemResolver(catalog.data).resolve(query.name)
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
        orders = [o for o in snapshot.data if self.visible(o, effective)]
        card = Card(
            title=item.name(),
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
            stale=snapshot.stale or details.stale,
            notes=[
                f"匹配物品：{item.slug} · PC / Crossplay · 等级：{rank if rank is not None else '不适用'}",
                "仅展示在线/游戏中的可见订单；价格单位为白金。挂单价不等于成交价。",
                "成交统计暂不可用；以下为当前挂单。",
            ],
        )
        if catalog.stale:
            card.notes.append(
                f"物品目录使用过期缓存，目录获取时间：{catalog.fetched_at:%Y-%m-%d %H:%M} UTC"
            )
        for side, label, limit in [("sell", "卖单（低价优先）", 5), ("buy", "买单（高价优先）", 3)]:
            selected = sorted(
                [o for o in orders if o.type == side],
                key=lambda o: (
                    o.platinum if side == "sell" else -o.platinum,
                    -o.updated_at.timestamp(),
                ),
            )[:limit]
            section = Section(
                title=label,
                columns=["玩家 / 状态 / 平台", "单价", "每次交易", "库存", "等级 / 子类型 / 属性"],
            )
            for order in selected:
                status = "游戏中" if order.user.status == "ingame" else "在线"
                traits = [str(order.rank) if order.rank is not None else "—", order.subtype or "—"]
                for name, value in [
                    ("充能", order.charges),
                    ("琥珀星", order.amber_stars),
                    ("青蓝星", order.cyan_stars),
                ]:
                    if value is not None:
                        traits.append(f"{name} {value}")
                section.rows.append(
                    [
                        f"{order.user.name} / {status} / {order.user.platform}",
                        str(order.platinum),
                        f"{order.per_trade} 件 / {order.platinum * order.per_trade} 白金",
                        str(order.quantity),
                        " / ".join(traits),
                    ]
                )
            if not selected:
                section.notes.append("暂无符合条件的在线挂单。")
            card.sections.append(section)
            if side == "sell" and selected:
                best = selected[0]
                rank_label = f" (rank {best.rank})" if best.rank is not None else ""
                command = (
                    f"/w {best.user.name} Hi! I want to buy: x{best.per_trade} "
                    f'"{item.name("en")}{rank_label}" for '
                    f"{best.platinum * best.per_trade} platinum. (warframe.market)"
                )
                card.sections.append(Section(title="最低卖单私聊指令", rows=[[command]]))
        if not orders:
            card.status = DataStatus.EMPTY
        return card

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
