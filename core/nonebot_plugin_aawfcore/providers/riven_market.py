# Desc: 通过共享 Market 限流器缓存 V1 紫卡拍卖搜索。
# Date: 2026-11-14
# Author: Aameow

from urllib.parse import urlencode

from ..infrastructure.cache import AsyncTTLCache
from ..models.common import Snapshot

API = "https://api.warframe.market/v1/auctions/search"


class RivenMarketProvider:
    def __init__(self, http, ttl=30):
        self.http = http
        self.cache = AsyncTTLCache[Snapshot](ttl, 90, max_entries=128)

    async def search(self, weapon, query):
        key = (weapon, tuple(sorted(query.positives)), query.negative)

        async def load():
            params = {"type": "riven", "weapon_url_name": weapon, "sort_by": "price_asc"}
            if query.unrolled:
                params.update(buyout_policy="direct", re_rolls_min=0, re_rolls_max=0)
            if query.positives:
                params["positive_stats"] = ",".join(sorted(query.positives))
            if query.negative is not None:
                params["negative_stats"] = query.negative
            url = API + "?" + urlencode(params)
            data = await self.http.get_json(url, market=True, headers={"Platform": "pc", "Language": "en", "Crossplay": "true"})
            rows = data.get("payload", {}).get("auctions") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ValueError("Market 紫卡拍卖数据格式异常")
            return Snapshot(data=rows, source=url)

        return await self.cache.get(key, load)

    async def close(self):
        await self.cache.close()
