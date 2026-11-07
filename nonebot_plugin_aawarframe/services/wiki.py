from ..models.wiki import WikiSearchResult
from ..providers.wiki import WikiProvider


class WikiService:
    def __init__(self, provider: WikiProvider):
        self.provider = provider

    async def search(self, query: str) -> WikiSearchResult:
        snapshot = await self.provider.search(query)
        return snapshot.data
