# 作用：实现 services 层的 wiki 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from ..grq import get_grq
from ..models.wiki import WikiSearchResult
from ..providers.wiki import WikiProvider


class WikiService:
    def __init__(self, provider: WikiProvider):
        self.provider = provider

    async def search(self, query: str) -> WikiSearchResult:
        result = get_grq().search("Items", query)
        if result.resource:
            query = result.resource.name()
        snapshot = await self.provider.search(query)
        return snapshot.data
