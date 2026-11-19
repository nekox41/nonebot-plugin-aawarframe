"""Wiki search uses raw keywords, bypasses game-item fuzzy matching entirely."""

from pathlib import Path

from ..models.wiki import WikiSearchResult
from ..providers.wiki import WikiProvider
from .wiki_store import WikiStore


class WikiService:
    def __init__(self, provider: WikiProvider, cache_path: Path | None = None):
        self.provider = provider
        self.store = WikiStore(cache_path)

    async def search(self, query: str) -> WikiSearchResult:
        keyword = query.strip()
        cached = self.store.get(keyword)
        if cached is not None:
            return cached
        snapshot = await self.provider.search(keyword)
        result = snapshot.data
        self.store.put(keyword, result)
        return result

    def close(self) -> None:
        self.store.close()
