import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.commands.parsing import parse_wiki_query
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.models.wiki import OpenSearchResponse
from nonebot_plugin_aawarframe.providers.wiki import WikiProvider
from nonebot_plugin_aawarframe.rendering.viewmodels import wiki_text
from nonebot_plugin_aawarframe.services.help import help_card
from nonebot_plugin_aawarframe.services.wiki import WikiService


@pytest.fixture
def wiki_response():
    return json.loads((Path(__file__).parent / "fixtures/wiki-search.json").read_text())


def test_documented_response_format(wiki_response):
    result = OpenSearchResponse.model_validate(wiki_response).to_result()
    expected = "\n\n".join(
        f"{title}\n{description}\n{url}"
        for title, description, url in zip(*wiki_response[1:], strict=True)
    )
    assert wiki_text(result) == expected
    assert len(result.entries) == 3


def test_empty_response():
    result = OpenSearchResponse.model_validate(["伯斯伯", [], [], []]).to_result()
    assert wiki_text(result) == "未找到与“伯斯伯”相关的 Wiki 条目。"


@pytest.mark.parametrize(
    "raw",
    [
        {},
        ["foo", [], []],
        ["foo", ["name"], [], []],
        ["foo", [3], ["desc"], ["https://warframe.huijiwiki.com/wiki/test"]],
        ["foo", ["name"], ["desc"], ["javascript:alert(1)"]],
        ["foo", ["name"], ["desc"], ["https://other.example/wiki/test"]],
    ],
)
def test_invalid_responses_are_not_silently_truncated(raw):
    with pytest.raises(ValueError):
        OpenSearchResponse.model_validate(raw).to_result()


@pytest.mark.parametrize("text", ["", " \n\t", "字" * 201])
def test_invalid_query(text):
    with pytest.raises(UserInputError):
        parse_wiki_query(text)


def test_keyword_preserves_internal_spaces():
    assert parse_wiki_query("  Frost Prime  ") == "Frost Prime"


async def test_provider_encoding_and_shared_cache(wiki_response):
    requests = []
    query = "伯斯顿 Prime&limit=999#test"

    async def load(url, *, headers):
        request = httpx.Request("GET", url, headers=headers)
        requests.append(request)
        assert request.url.host == "warframe.huijiwiki.com"
        assert request.url.params["search"] == query
        assert request.url.params["limit"] == "10"
        assert request.url.params["action"] == "opensearch"
        assert request.url.params["formatversion"] == "2"
        assert request.url.params["suggest"] == "true"
        assert request.url.params["_referrer"] == "warframe.huijiwiki.com"
        assert request.headers["Accept-Language"] == "zh-CN,zh;q=0.9"
        assert "Cookie" not in request.headers and "Authorization" not in request.headers
        return wiki_response

    browser = SimpleNamespace(get_json=AsyncMock(side_effect=load))
    provider = WikiProvider(browser)
    service = WikiService(provider)
    results = await asyncio.gather(*(service.search(query) for _ in range(10)))
    assert len(requests) == 1 and len(results[0].entries) == 3
    await service.search(query)
    assert len(requests) == 1
    await provider.close()


async def test_command_is_text_only_and_does_not_interpret_cq_codes(wiki_response, monkeypatch):
    wiki_response[1][0] = "[CQ:image,file=example]"
    result = OpenSearchResponse.model_validate(wiki_response).to_result()
    runtime = SimpleNamespace(
        wiki=SimpleNamespace(search=AsyncMock(return_value=result)),
        renderer=SimpleNamespace(render=AsyncMock()),
    )
    monkeypatch.setattr(router, "get_runtime", lambda: runtime)
    message = await router.dispatch("wiki", " 伯斯顿 ")
    assert all(segment.type == "text" for segment in message)
    assert "[CQ:image,file=example]" in message.extract_plain_text()
    runtime.wiki.search.assert_awaited_once_with("伯斯顿")
    runtime.renderer.render.assert_not_awaited()


async def test_empty_keyword_skips_http_and_failure_is_text(monkeypatch):
    runtime = SimpleNamespace(
        wiki=SimpleNamespace(search=AsyncMock(side_effect=OSError("unavailable")))
    )
    monkeypatch.setattr(router, "get_runtime", lambda: runtime)
    assert "用法：wk" in (await router.dispatch("wiki", " ")).extract_plain_text()
    runtime.wiki.search.assert_not_awaited()
    message = await router.dispatch("wiki", "伯斯顿")
    assert "暂时不可用" in message.extract_plain_text()
    assert all(segment.type == "text" for segment in message)


def test_command_and_alias_registration(monkeypatch):
    registrations = []
    monkeypatch.setattr(router, "register", lambda *args: registrations.append(args))
    router.setup()
    assert ("wk", {"wiki"}, "wiki") in registrations
    assert "wk 关键词 / wiki 关键词" in help_card().text()
