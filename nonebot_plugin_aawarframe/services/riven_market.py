# Desc: 查询零洗直售或按正负词条筛选的紫卡挂单。
# Date: 2026-11-14
# Author: Aameow

from math import log
from statistics import median

from ..localization.riven_attributes import allowed, attribute_value, attributes
from ..localization.rivens import resolve_riven_weapon
from ..models.common import Card, DataStatus
from ..models.errors import UserInputError
from ..models.riven_market import RivenListing, RivenMarketBoard

STATUSES = {"ingame": "游戏中", "online": "在线", "offline": "离线", "invisible": "离线"}


def unrolled_listings(listings):
    listings = [item for item in listings if item.price > 0]
    if len(listings) >= 5:
        # 对数价格上的三倍稳健标准差，只排除低端异常，不让天价挂单拉高均值。
        prices = [log(item.price) for item in listings]
        center = median(prices)
        deviation = 1.4826 * median(abs(price - center) for price in prices)
        # 价格完全集中时，只剔除比中位价低一个数量级的挂单。
        lower = center - (3 * deviation if deviation else log(10))
        listings = [item for item in listings if log(item.price) + 1e-12 >= lower]
    return sorted(listings, key=lambda item: item.price)[:10]


class RivenMarketService:
    def __init__(self, provider):
        self.provider = provider

    async def query(self, query):
        weapon = resolve_riven_weapon(query.weapon)
        kind = weapon.metadata.get("weapon_type")
        if kind not in {"rifle", "shotgun", "pistol", "archgun", "melee", "zaw", "kitgun"}:
            kind = weapon.metadata.get("rivenType")
        catalog = attributes()
        for slug in query.positives:
            if not allowed(catalog[slug], kind, True):
                raise UserInputError(f"{weapon.name()}不能获得正面词条“{catalog[slug]['short']}”。发送“词条”查看映射。")
        if query.negative not in {None, "has"} and not allowed(catalog[query.negative], kind, False):
            raise UserInputError(f"{weapon.name()}不能获得负面词条“{catalog[query.negative]['short']}”。发送“词条”查看映射。")
        slug = weapon.metadata.get("slug") or weapon.id
        snapshot = await self.provider.search(slug, query)
        board = RivenMarketBoard(weapon=weapon.name(), positive_filter="0 洗直售 · 价格升序" if query.unrolled else " · ".join(catalog[s]["short"] for s in query.positives) or "正面不限", negative_filter="不限制负面" if query.negative is None else "任意负面" if query.negative == "has" else "负" + catalog[query.negative]["short"])
        for row in snapshot.data:
            if not isinstance(row, dict) or row.get("closed") or row.get("private") or not row.get("visible", False):
                continue
            if row.get("platform") != "pc" and not row.get("crossplay"):
                continue
            item, owner = row.get("item", {}), row.get("owner", {})
            if item.get("type") != "riven" or item.get("weapon_url_name") != slug:
                continue
            if query.unrolled and (item.get("re_rolls") != 0 or not row.get("is_direct_sell")):
                continue
            stats = item.get("attributes", [])
            pos = {s["url_name"] for s in stats if s.get("positive") is True}
            neg = {s["url_name"] for s in stats if s.get("positive") is False}
            if not set(query.positives) <= pos or (query.negative == "has" and not neg) or (query.negative not in {None, "has"} and query.negative not in neg):
                continue
            direct = row.get("is_direct_sell", False)
            price = row.get("buyout_price")
            label = "标价" if direct else "一口价"
            if price is None:
                price, label = row.get("starting_price"), "起拍"
            if not isinstance(price, int) or price < 0 or not owner.get("ingame_name"):
                continue
            positive, negative = [], []
            for stat in stats:
                attribute = catalog.get(stat.get("url_name"))
                value = stat.get("value")
                if not isinstance(value, (int, float)):
                    continue
                name = attribute["short"] if attribute else stat.get("url_name", "未知词条")
                formatted = attribute_value(attribute, value, stat["positive"]) if attribute else str(value)
                (positive if stat["positive"] else negative).append(name + " " + formatted)
            board.listings.append(RivenListing(seller=owner["ingame_name"], status=STATUSES.get(owner.get("status"), "离线"), price=price, price_type=label, rank=item.get("mod_rank", 0), mastery=item.get("mastery_level", 0), rolls=item.get("re_rolls", 0), positives=positive, negatives=negative))
            if not query.unrolled and len(board.listings) == 10:
                break
        if query.unrolled:
            board.listings = unrolled_listings(board.listings)
        return Card(title=weapon.name() + " · 紫卡挂单", source=snapshot.source, fetched_at=snapshot.fetched_at, stale=snapshot.stale, riven_market_board=board, status=DataStatus.OK if board.listings else DataStatus.EMPTY)
