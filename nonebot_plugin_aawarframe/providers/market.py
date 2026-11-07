import logging
from datetime import timedelta
from pathlib import Path

from pydantic import TypeAdapter

from ..infrastructure.cache import AsyncTTLCache
from ..infrastructure.http import HttpClient
from ..infrastructure.storage import read_json, write_json
from ..models.common import Snapshot, utcnow
from ..models.market import Item, MarketQuery, Order

logger = logging.getLogger(__name__)
MARKET_URL = "https://api.warframe.market/v2"
ITEMS = TypeAdapter(list[Item])
ORDERS = TypeAdapter(list[Order])


class MarketProvider:
    def __init__(self, http: HttpClient, cache_dir: Path, ttl: float = 30):
        self.http = http
        self.catalog_path = cache_dir / "market-items.json"
        self.cache = AsyncTTLCache[Snapshot](ttl, 90)
        self.catalog_cache = AsyncTTLCache[Snapshot](3600, 86400)

    async def request(self, path: str, *, platform: str = "pc", crossplay: bool = True):
        result = await self.http.get_json(
            MARKET_URL + path,
            market=True,
            headers={
                "Language": "zh-hans",
                "Platform": platform,
                "Crossplay": str(crossplay).lower(),
            },
        )
        if not isinstance(result, dict) or result.get("error") or result.get("data") is None:
            raise ValueError("Market 返回无效数据")
        return result["data"]

    async def catalog(self) -> Snapshot:
        async def load():
            persisted = await read_json(self.catalog_path)
            try:
                versions = await self.request("/versions")
                version = versions["collections"]["items"]
                if persisted and persisted.get("version") == version:
                    items = ITEMS.validate_python(persisted["items"])
                else:
                    items = ITEMS.validate_python(await self.request("/items"))
                if not items:
                    raise ValueError("Market 目录为空")
                result = Snapshot(data=items, source=MARKET_URL + "/items")
                await write_json(
                    self.catalog_path,
                    {
                        "version": version,
                        "items": [i.model_dump(by_alias=True) for i in items],
                        "fetched_at": result.fetched_at.isoformat(),
                    },
                )
                return result
            except Exception:
                if persisted:
                    try:
                        old = Snapshot(
                            data=ITEMS.validate_python(persisted["items"]),
                            source=MARKET_URL + "/items",
                            fetched_at=persisted["fetched_at"],
                            stale=True,
                        )
                        if old.data and timedelta(0) <= utcnow() - old.fetched_at <= timedelta(
                            days=1
                        ):
                            logger.warning("目录更新失败，使用本地缓存", exc_info=True)
                            return old
                    except (KeyError, ValueError, TypeError):
                        pass
                raise

        return await self.catalog_cache.get("zh-hans", load)

    async def item(self, slug: str) -> Snapshot:
        async def load():
            return Snapshot(
                data=Item.model_validate(await self.request("/item/" + slug)),
                source=MARKET_URL + "/item/" + slug,
            )

        return await self.cache.get(("item", slug, "zh-hans"), load)

    async def orders(self, slug: str, query: MarketQuery) -> Snapshot:
        key = ("orders", slug, query.rank, query.subtype, query.platform, query.crossplay)

        async def load():
            data = await self.request(
                "/orders/item/" + slug, platform=query.platform, crossplay=query.crossplay
            )
            return Snapshot(
                data=ORDERS.validate_python(data), source=MARKET_URL + "/orders/item/" + slug
            )

        return await self.cache.get(key, load)

    async def close(self) -> None:
        await self.cache.close()
        await self.catalog_cache.close()
