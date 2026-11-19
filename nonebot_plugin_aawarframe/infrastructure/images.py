# Desc: 共享物品图片缓存及并发限制。
# Date: 2026-11-14
# Author: Aameow

import asyncio
import base64
import re
from time import monotonic
from urllib.parse import urlsplit

import httpx

from ..models.common import Snapshot
from .cache import AsyncTTLCache


class ItemImages:
    def __init__(self, http):
        self.http = http
        self.cache = AsyncTTLCache[Snapshot](86400, 86400, max_entries=256)
        self.limit = asyncio.Semaphore(4)
        self.failed_until = {}

    async def get(self, resource, extra_urls=()):
        name = resource.metadata.get("imageName", "") if resource else ""
        urls = []
        if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            urls.append("https://raw.githubusercontent.com/WFCD/warframe-items/master/data/img/" + name)
        for url in [*urls, *extra_urls]:
            async def load(target=url):
                async with self.limit:
                    host = urlsplit(target).netloc
                    if self.failed_until.get(host, 0) > monotonic():
                        raise ConnectionError("图片来源暂不可用")
                    try:
                        response = await asyncio.wait_for(self.http.get_response(target), 8)
                    except (httpx.TransportError, TimeoutError):
                        self.failed_until[host] = monotonic() + 60
                        raise
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code != 404:
                            self.failed_until[host] = monotonic() + 60
                        raise
                mime = response.headers.get("content-type", "").split(";", 1)[0]
                if mime not in {"image/png", "image/jpeg", "image/webp"} or len(response.content) > 4_000_000:
                    raise ValueError("无效的物品图片")
                return Snapshot(data="data:" + mime + ";base64," + base64.b64encode(response.content).decode(), source=target)
            try:
                return (await self.cache.get(url, load)).data
            except Exception:
                continue
        return ""

    async def close(self):
        await self.cache.close()
