from urllib.parse import urlencode

from ..infrastructure.cache import AsyncTTLCache
from ..infrastructure.wiki_browser import WikiBrowserClient
from ..models.common import Snapshot
from ..models.wiki import OpenSearchResponse

WIKI_API = "https://warframe.huijiwiki.com/api.php"


class WikiProvider:
    def __init__(self, browser: WikiBrowserClient):
        self.browser = browser
        self.cache = AsyncTTLCache[Snapshot](300, 0)

    async def search(self, query: str) -> Snapshot:
        async def load():
            parameters = {
                "action": "opensearch",
                "format": "json",
                "search": query,
                "limit": "10",
            }
            raw = await self.browser.get_json(
                WIKI_API + "?" + urlencode(parameters),
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )
            result = OpenSearchResponse.model_validate(raw).to_result()
            return Snapshot(data=result, source=WIKI_API)

        return await self.cache.get(query, load)

    async def close(self) -> None:
        await self.cache.close()
