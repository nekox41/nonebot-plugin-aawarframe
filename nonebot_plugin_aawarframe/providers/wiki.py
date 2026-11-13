# 作用：实现 providers 层的 wiki 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from urllib.parse import urlencode

from ..infrastructure.cache import AsyncTTLCache
from ..infrastructure.wiki_http import WikiHttpClient
from ..models.common import Snapshot
from ..models.wiki import WIKI_RESULT_LIMIT, OpenSearchResponse

WIKI_API = "http://warframe.huijiwiki.com/api.php"


class WikiProvider:
    def __init__(self, http: WikiHttpClient):
        self.http = http
        self.cache = AsyncTTLCache[Snapshot](300, 0)

    async def search(self, query: str) -> Snapshot:
        async def load():
            parameters = {
                "action": "opensearch",
                "format": "json",
                "formatversion": "2",
                "suggest": "true",
                "_referrer": "warframe.huijiwiki.com",
                "search": query,
                "limit": str(WIKI_RESULT_LIMIT),
            }
            raw = await self.http.get_json(
                WIKI_API + "?" + urlencode(parameters),
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN",
                },
            )
            result = OpenSearchResponse.model_validate(raw).to_result()
            return Snapshot(data=result, source=WIKI_API)

        return await self.cache.get(query, load)

    async def close(self) -> None:
        await self.cache.close()
