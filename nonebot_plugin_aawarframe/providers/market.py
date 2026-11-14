# Desc: 获取 Market 物品与 Top 订单，缓存物品图片。
# Date: 2026-11-14
# Author: Aameow

import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

from pydantic import TypeAdapter

from ..grq import get_grq
from ..infrastructure.cache import AsyncTTLCache
from ..infrastructure.images import ItemImages
from ..infrastructure.http import HttpClient
from ..infrastructure.storage import read_json, write_json
from ..models.common import Snapshot, utcnow
from ..models.market import Item, MarketQuery, TopOrders

logger = logging.getLogger(__name__)
MARKET_URL = "https://api.warframe.market/v2"
ITEMS = TypeAdapter(list[Item])


class MarketProvider:
    def __init__(self, http: HttpClient, cache_dir: Path, ttl: float = 30, images=None):
        self.http = http
        self.catalog_path = cache_dir / "market-items.json"
        self.cache = AsyncTTLCache[Snapshot](ttl, 90)
        self.images = images or ItemImages(http)
        self.owns_images = images is None
        self.catalog_cache = AsyncTTLCache[Snapshot](3600, 86400)

    async def request(
        self, path: str, *, platform: str = "pc", crossplay: bool = True, params: dict | None = None
    ):
        result = await self.http.get_json(
            MARKET_URL + path + ("?" + urlencode(params) if params else ""),
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
                "/orders/item/" + slug + "/top",
                platform=query.platform,
                crossplay=query.crossplay,
                params={
                    key: value
                    for key, value in {"rank": query.rank, "subtype": query.subtype}.items()
                    if value is not None
                },
            )
            return Snapshot(
                data=TopOrders.model_validate(data),
                source=MARKET_URL + "/orders/item/" + slug + "/top",
            )

        return await self.cache.get(key, load)

    async def icon(self, item: Item) -> str:
        resource = get_grq().get("Items", item.slug, "market.slug")
        localized = item.i18n.get("zh-hans") or item.i18n.get("en")
        path = (localized.icon or localized.thumb) if localized else ""
        url = urljoin("https://warframe.market/static/assets/", path)
        parsed = urlsplit(url)
        urls = [url] if path and parsed.scheme == "https" and parsed.netloc == "warframe.market" and parsed.path.startswith("/static/assets/") else []
        return await self.images.get(resource, urls)

    async def close(self) -> None:
        if self.owns_images:
            await self.images.close()
        await self.cache.close()
        await self.catalog_cache.close()
