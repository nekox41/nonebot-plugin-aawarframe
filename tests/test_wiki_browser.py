# 作用：验证 wiki_browser 相关行为。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.infrastructure.wiki_browser import WikiBrowserClient
from nonebot_plugin_aawarframe.models.errors import WikiChallengeError
from nonebot_plugin_aawarframe.providers.wiki import WikiProvider


class Pages:
    def __init__(self, response):
        self.page = SimpleNamespace(
            set_extra_http_headers=AsyncMock(), goto=AsyncMock(return_value=response)
        )
        self.opened = self.closed = self.active = self.maximum = 0

    @asynccontextmanager
    async def open(self):
        self.opened += 1
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            yield self.page
        finally:
            self.active -= 1
            self.closed += 1


def response(status=200, *, content_type="application/json; charset=utf-8", challenge=False):
    return SimpleNamespace(
        status=status,
        ok=200 <= status < 300,
        headers={
            "content-type": content_type,
            **({"cf-mitigated": "challenge"} if challenge else {}),
        },
        json=AsyncMock(return_value=["Te", [], [], []]),
    )


async def test_borrows_existing_htmlrender_browser(monkeypatch):
    import nonebot_plugin_htmlrender

    pages = Pages(response())
    options = []

    def page(**kwargs):
        options.append(kwargs)
        return pages.open()

    app = SimpleNamespace(extensions=SimpleNamespace(playwright=SimpleNamespace(page=page)))
    monkeypatch.setattr(nonebot_plugin_htmlrender, "get_default_application", lambda: app)
    result = await WikiBrowserClient().get_json(
        "https://warframe.huijiwiki.com/api.php?search=Te", headers={"Accept": "application/json"}
    )
    assert result == ["Te", [], [], []]
    assert options == [{"locale": "zh-CN"}]
    assert pages.opened == pages.closed == 1
    pages.page.set_extra_http_headers.assert_awaited_once_with({"Accept": "application/json"})
    assert pages.page.goto.call_args.kwargs["wait_until"] == "domcontentloaded"


@pytest.mark.parametrize("status", [200, 403])
async def test_challenge_is_not_cached_or_parsed_as_json(status):
    blocked = response(status, challenge=True, content_type="text/html")
    pages = Pages(blocked)
    provider = WikiProvider(WikiBrowserClient(page_factory=pages.open))
    for _ in range(2):
        with pytest.raises(WikiChallengeError):
            await provider.search("Te")
    assert pages.opened == pages.closed == 2
    blocked.json.assert_not_awaited()
    await provider.close()


@pytest.mark.parametrize(
    "reply", [None, response(500), response(304), response(content_type="text/html")]
)
async def test_bad_response_closes_page(reply):
    pages = Pages(reply)
    with pytest.raises(RuntimeError):
        await WikiBrowserClient(page_factory=pages.open).get_json(
            "https://warframe.huijiwiki.com/api.php"
        )
    assert pages.opened == pages.closed == 1
    if reply:
        reply.json.assert_not_awaited()


async def test_timeout_releases_page():
    pages = Pages(response())

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    pages.page.goto.side_effect = hang
    with pytest.raises(TimeoutError):
        await WikiBrowserClient(timeout=0.02, page_factory=pages.open).get_json(
            "https://warframe.huijiwiki.com/api.php"
        )
    assert pages.closed == 1 and pages.active == 0


async def test_json_error_releases_page():
    reply = response()
    reply.json.side_effect = ValueError("bad JSON")
    pages = Pages(reply)
    with pytest.raises(ValueError):
        await WikiBrowserClient(page_factory=pages.open).get_json(
            "https://warframe.huijiwiki.com/api.php"
        )
    assert pages.closed == 1


async def test_browser_queries_are_serialized():
    pages = Pages(response())

    async def navigate(*args, **kwargs):
        await asyncio.sleep(0.01)
        return response()

    pages.page.goto.side_effect = navigate
    browser = WikiBrowserClient(page_factory=pages.open)
    await asyncio.gather(
        *(browser.get_json("https://warframe.huijiwiki.com/api.php") for _ in range(5))
    )
    assert pages.maximum == 1 and pages.closed == 5


async def test_shutdown_cancels_navigation_and_closes_page():
    pages = Pages(response())
    started = asyncio.Event()

    async def navigate(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    pages.page.goto.side_effect = navigate
    provider = WikiProvider(WikiBrowserClient(page_factory=pages.open))
    task = asyncio.create_task(provider.search("Te"))
    await started.wait()
    await provider.close()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pages.closed == 1


async def test_challenge_message_is_clear_and_text_only(monkeypatch):
    runtime = SimpleNamespace(
        wiki=SimpleNamespace(search=AsyncMock(side_effect=WikiChallengeError()))
    )
    monkeypatch.setattr(router, "get_runtime", lambda: runtime)
    message = await router.dispatch("wiki", "Te")
    assert "要求浏览器验证" in message.extract_plain_text()
    assert all(segment.type == "text" for segment in message)
