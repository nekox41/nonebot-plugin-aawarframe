# 作用：实现 providers 层的 worldstate 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from pathlib import Path

from ..infrastructure.cache import AsyncTTLCache
from ..infrastructure.http import HttpClient
from ..infrastructure.storage import write_json
from ..models.common import Snapshot

WORLDSTATE_URL = "https://api.warframe.com/cdn/worldState.php"


class WorldStateProvider:
    def __init__(self, http: HttpClient, cache_dir: Path, ttl: float = 45):
        self.http = http
        self.cache_dir = cache_dir
        self.cache = AsyncTTLCache[Snapshot](ttl, 180)

    async def fetch(self) -> Snapshot:
        async def load():
            data = await self.http.get_json(WORLDSTATE_URL)
            if not isinstance(data, dict) or not data:
                raise ValueError("官方世界状态不是有效对象")
            snapshot = Snapshot(data=data, source=WORLDSTATE_URL)
            await write_json(
                self.cache_dir / "worldstate-latest.json", snapshot.model_dump(mode="json")
            )
            return snapshot

        return await self.cache.get("pc", load)

    async def close(self) -> None:
        await self.cache.close()
