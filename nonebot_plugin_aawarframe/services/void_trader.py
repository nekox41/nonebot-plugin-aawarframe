# Desc: 查询本次虚空商人货单，分类展示。
# Date: 2026-11-14
# Author: Aameow

from ..grq import get_grq
from ..localization.resolver import node_info
from ..models.common import DataStatus, utcnow
from ..models.void_trader import TraderBoard, TraderGroup, TraderItem, VoidTrader
from ..worldstate.parsers.common import records
from .common import card_for
from .weekly import item_name

WEAPONS = {"Primary", "Secondary", "Melee", "Arch-Gun", "Arch-Melee", "SentinelWeapons"}
APPEARANCE = {"Skins", "Sigils", "Glyphs", "Emotes"}


def category(resource, path):
    meta = resource.metadata if resource else {}
    kind = meta.get("category", "")
    if kind == "Mods" or "/upgrades/mods/" in path.lower():
        return "Mod"
    if kind in WEAPONS:
        return "武器"
    text = (path + " " + str(meta.get("type", ""))).lower()
    if kind in APPEARANCE or any(word in text for word in ("skin", "scarf", "syandana", "sugatra", "armor", "ephemera", "sigil", "glyph", "emote", "colour", "color", "deco", "attachment")):
        return "外观"
    return "武器" if "/weapons/" in path.lower() else "其他杂项"


class VoidTraderService:
    def __init__(self, provider):
        self.provider = provider

    async def query(self):
        snapshot = await self.provider.fetch()
        now = utcnow()
        traders, warnings = records(snapshot.data, "VoidTraders", VoidTrader)
        card = card_for(snapshot, "虚空商人")
        card.notes = warnings
        board = card.trader_board = TraderBoard()
        active = [t for t in traders if t.activation <= now < t.expiry]
        if not active:
            future = [t for t in traders if t.activation > now]
            if future:
                trader = min(future, key=lambda t: t.activation)
                board.location = self.location(trader.node)
                board.time, board.time_label = trader.activation, "到访时间"
            board.message = "虚空商人尚未到访，货单暂未开放。" if future else "虚空商人当前未到访。"
            card.status = DataStatus.EMPTY
            return card
        board.location = "、".join(dict.fromkeys(self.location(t.node) for t in active))
        board.time = min(t.expiry for t in active)
        groups = {name: [] for name in ("Mod", "武器", "外观", "其他杂项")}
        grq = get_grq()
        for trader in active:
            for offer in trader.manifest:
                if offer.type.rsplit("/", 1)[-1].casefold() == "barotreasurebox":
                    continue
                resource = grq.get("Items", offer.type, "game.ref") or grq.get(
                    "Items", offer.type.replace("/StoreItems/", "/"), "game.ref"
                )
                name = item_name(offer.type)
                if name == "虚空余货":
                    continue
                if resource is None:
                    match = grq.search("Items", name)
                    if match.exact and match.resource:
                        resource = grq.get("Items", match.resource.id)
                item = TraderItem(name=name, ducats=offer.ducats, credits=offer.credits,
                                  location=self.location(trader.node) if len(active) > 1 else "")
                groups[category(resource, offer.type)].append(item)
        board.groups = [TraderGroup(name=name, items=items) for name, items in groups.items() if items]
        if not board.groups:
            board.message = "本次货单暂未公布。"
            card.status = DataStatus.EMPTY
        return card

    @staticmethod
    def location(node):
        info = node_info(node)
        return " / ".join(filter(None, (info.get("name", node), info.get("systemName"))))
