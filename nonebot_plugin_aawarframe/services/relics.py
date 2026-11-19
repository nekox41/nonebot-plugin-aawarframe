# Desc: 反查部件掉落遗物，并为遗物奖励汇总 WM 在线卖价。
# Date: 2026-11-15
# Author: Aameow

import asyncio
import logging
from collections import Counter

from ..grq import get_grq
from ..localization.relics import RelicIndex
from ..models.common import Card, utcnow
from ..models.errors import UserInputError
from ..models.market import MarketQuery
from ..models.relics import PartRelics, PartsBoard, RelicBoard
from .market import MarketService

logger = logging.getLogger(__name__)


class RelicService:
    def __init__(self, market):
        self.market = market
        self.index = RelicIndex()

    def part_card(self, query):
        grq = get_grq()
        resource = self.index.item(query)
        quantities, names = Counter(), {}

        def visit(ref, quantity, seen):
            key = self.index.canonical(ref)
            if key in seen:
                return
            item = grq.get("Items", ref, "game.ref")
            if key in self.index.reverse:
                source = grq.get("Items", key, "game.ref")
                quantities[key] += quantity
                names[key] = source.name() if source else self.index.reward_items[key]["name"]
            elif item:
                components = item.metadata.get("components", [])
                if components:
                    for component in components:
                        visit(component["uniqueName"], quantity * component.get("itemCount", 1), seen | {key})
                elif item.metadata.get("category") == "Components":
                    quantities[key] += quantity
                    names[key] = item.name()

        visit(resource.identifiers.get("game.ref", resource.id), 1, set())
        if not quantities:
            raise UserInputError("该物品没有可查询的遗物部件。")
        parts = []
        for ref, quantity in quantities.items():
            entries = self.index.reverse.get(ref, {})
            keys = sorted(entries, key=lambda key: (self.index.relics[key]["era"], self.index.relics[key]["code"].rstrip("0123456789"), int("".join(filter(str.isdigit, self.index.relics[key]["code"])) or 0)))
            parts.append(PartRelics(name=names[ref], quantity=quantity, relics=[entries[key] for key in keys]))
        return Card(title=resource.name() + " · 部件遗物", source="WFCD / warframe-items", parts_board=PartsBoard(parts=parts))

    async def parts(self, query):
        await asyncio.to_thread(self.index.prepare)
        return await asyncio.to_thread(self.part_card, query)

    async def relic(self, query):
        await asyncio.to_thread(self.index.prepare)
        relic = self.index.relic(query)
        rewards = self.index.rewards(relic)
        catalog = None
        try:
            catalog = await self.market.catalog()
        except Exception:
            logger.warning("遗物奖励价格目录暂不可用", exc_info=True)
        items = {item.slug: item for item in catalog.data} if catalog else {}

        async def price(reward):
            if not reward.slug:
                return None
            item = items.get(reward.slug)
            if item is None:
                reward.price_status = "暂缺"
                return None
            if not item.tradable:
                return None
            query = MarketQuery(name=reward.name, rank=0 if item.max_rank is not None else None)
            try:
                snapshot = await self.market.orders(item.slug, query)
                orders = [o for o in snapshot.data.sell if o.type == "sell" and MarketService.visible(o, query)]
                if orders:
                    reward.price = min(o.platinum / o.per_trade for o in orders) * reward.quantity
                    reward.price_status = ""
                else:
                    reward.price_status = "无在线卖单"
                return snapshot
            except Exception:
                reward.price_status = "暂缺"
                logger.warning("遗物奖励价格暂缺：%s", item.slug, exc_info=True)
                return None

        snapshots = [s for s in await asyncio.gather(*(price(reward) for reward in rewards)) if s]
        return Card(title=relic["name"] + " · 遗物", source="WFCD / Warframe.market", relic_board=RelicBoard(name=relic["name"], vaulted=relic["vaulted"], rewards=rewards), fetched_at=min((s.fetched_at for s in snapshots), default=utcnow()), stale=any(s.stale for s in snapshots) or bool(catalog and catalog.stale))
