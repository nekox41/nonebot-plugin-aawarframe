"""Issue #16: Wiki must use the raw keyword and reuse only nonempty results."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawfcore.models.wiki import OpenSearchResponse
from nonebot_plugin_aawfcore.services.wiki import WikiService


def reply(keyword, title, description="页面描述"):
    return OpenSearchResponse.model_validate([
        keyword, [title], [description],
        ["https://warframe.huijiwiki.com/wiki/" + title],
    ]).to_result()


@pytest.mark.asyncio
async def test_raw_wiki_keywords_are_not_rewritten_to_game_item_names(tmp_path):
    provider = SimpleNamespace(search=AsyncMock(side_effect=lambda q: SimpleNamespace(
        data=reply(q, q),
    )))
    service = WikiService(provider, tmp_path / "wiki.sqlite3")
    try:
        for key in ("预言神密", "赋能消磁", "消磁"):
            assert (await service.search(key)).entries[0].title == key
        assert [call.args[0] for call in provider.search.await_args_list] == [
            "预言神密", "赋能消磁", "消磁",
        ]
    finally:
        service.close()


@pytest.mark.asyncio
async def test_cache_survives_restart_reuses_pages_and_preserves_order(tmp_path):
    path = tmp_path / "wiki.sqlite3"
    raw = OpenSearchResponse.model_validate([
        "伯斯顿", ["伯斯顿", "伯斯顿Prime", "伯斯顿灵化之源"],
        ["a", "b", "c"],
        ["https://warframe.huijiwiki.com/wiki/a",
         "https://warframe.huijiwiki.com/wiki/b",
         "https://warframe.huijiwiki.com/wiki/c"],
    ]).to_result()
    provider = SimpleNamespace(search=AsyncMock(return_value=SimpleNamespace(data=raw)))
    first = WikiService(provider, path)
    assert len((await first.search("伯斯顿")).entries) == 3
    first.close()

    second = WikiService(provider, path)
    try:
        result = await second.search("伯斯顿")
        assert [e.title for e in result.entries] == ["伯斯顿", "伯斯顿Prime", "伯斯顿灵化之源"]
        assert provider.search.await_count == 1
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0] == 3
            assert db.execute("SELECT COUNT(*) FROM wiki_keys").fetchone()[0] == 3
    finally:
        second.close()


@pytest.mark.asyncio
async def test_empty_results_and_upstream_errors_are_not_saved(tmp_path):
    path = tmp_path / "wiki.sqlite3"
    blank = OpenSearchResponse.model_validate(["不存在", [], [], []]).to_result()
    provider = SimpleNamespace(search=AsyncMock(return_value=SimpleNamespace(data=blank)))
    service = WikiService(provider, path)
    try:
        await service.search("不存在")
        await service.search("不存在")
        assert provider.search.await_count == 2
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM wiki_keys").fetchone()[0] == 0
        provider.search.side_effect = OSError("Wiki unavailable")
        with pytest.raises(OSError):
            await service.search("错误关键词")
    finally:
        service.close()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM wiki_keys").fetchone()[0] == 0
