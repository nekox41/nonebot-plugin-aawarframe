# 作用：验证 rendering 相关行为。
# 编写日期：2026-11-07
# 作者：Aameow

from types import SimpleNamespace
from unittest.mock import AsyncMock

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import Card, Section
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.rendering.viewmodels import paginate


def test_html_escapes_all_external_text():
    card = Card(
        title='<script>alert("x")</script>',
        source="fixture",
        sections=[Section(title="<img src=x>", rows=[["</td><script>evil()</script>"]])],
    )
    html = CardRenderer().html(card)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "https://fonts" not in html and 'lang="zh-CN"' in html


def test_pagination_retains_all_rows():
    rows = [[str(i), "说明" * 30] for i in range(70)]
    card = Card(title="长列表", source="fixture", sections=[Section(title="任务", rows=rows)])
    pages = paginate(card)
    assert len(pages) > 1
    assert [row for page in pages for section in page.sections for row in section.rows] == rows
    assert all(sum(len(section.rows) for section in page.sections) <= 12 for page in pages)


async def test_render_concurrency_cache_and_singleflight(monkeypatch):
    import asyncio

    import nonebot_plugin_htmlrender

    running = maximum = calls = 0

    async def render(html, **kwargs):
        nonlocal running, maximum, calls
        assert kwargs["width"] == 800
        calls += 1
        running += 1
        maximum = max(maximum, running)
        await asyncio.sleep(0.01)
        running -= 1
        return b"png"

    monkeypatch.setattr(nonebot_plugin_htmlrender, "render_html", render)
    monkeypatch.setattr(CardRenderer, "_encode_webp", AsyncMock(return_value=b"webp"))
    renderer = CardRenderer()
    first = Card(title="one", source="fixture")
    await asyncio.gather(*(renderer.render(first) for _ in range(5)))
    assert calls == 1
    await asyncio.gather(*(renderer.render(Card(title=str(i), source="fixture")) for i in range(6)))
    assert maximum == 2
    await renderer.close()


async def test_render_failure_falls_back_to_data_text():
    card = Card(
        title="氏族奖励",
        source="fixture",
        stale=True,
        sections=[Section(title="奖励", rows=[["Endo", "100"]])],
    )
    runtime = SimpleNamespace(
        renderer=SimpleNamespace(render=AsyncMock(side_effect=RuntimeError("browser down")))
    )
    result = await router.response(card, runtime)
    text = result.extract_plain_text()
    assert "Endo | 100" in text and "过期缓存" in text and "UTC" in text


async def test_command_rejects_unknown_parameters_and_isolates_upstream(monkeypatch):
    runtime = SimpleNamespace(
        world=SimpleNamespace(query=AsyncMock(side_effect=OSError("offline")))
    )
    monkeypatch.setattr(router, "get_runtime", lambda: runtime)
    assert "不接受参数" in (await router.dispatch("fissures", "extra")).extract_plain_text()
    runtime.world.query.assert_not_awaited()
    assert "暂时不可用" in (await router.dispatch("fissures")).extract_plain_text()


async def test_lifecycle_closes_http_and_resets_runtime(monkeypatch, tmp_path):
    from nonebot_plugin_aawarframe.bootstrap import Runtime
    from nonebot_plugin_aawarframe.config import Config

    runtime = Runtime(Config(aawarframe_cache_dir=tmp_path))
    await runtime.close()
    assert runtime.http.client.is_closed
    assert {p.name for p in tmp_path.iterdir()} == {"registry.sqlite3", "resources"}
    assert (tmp_path / "resources/current.json").exists()


def test_fallback_is_concise_and_preserves_provenance():
    from nonebot_plugin_aawarframe.rendering.viewmodels import fallback_text

    card = Card(
        title="长赏金列表",
        source="fixture",
        stale=True,
        sections=[Section(title="奖励", rows=[[str(i), "奖励内容" * 20] for i in range(200)])],
    )
    text = fallback_text(card)
    assert len(text) <= 1800
    assert "仅显示部分结果" in text
    assert "过期缓存" in text and "来源：fixture" in text and "UTC" in text


async def test_worldstate_proxy_does_not_route_market_or_napcat(monkeypatch, tmp_path):
    from nonebot_plugin_aawarframe import bootstrap
    from nonebot_plugin_aawarframe.config import Config

    clients = []

    class FakeHttp:
        def __init__(self, timeout, *, proxy=None):
            self.proxy = proxy
            self.client = SimpleNamespace(timeout=None)
            self.closed = False
            clients.append(self)

        async def close(self):
            self.closed = True

    monkeypatch.setattr(bootstrap, "HttpClient", FakeHttp)
    runtime = bootstrap.Runtime(
        Config(
            aawarframe_cache_dir=tmp_path, aawarframe_worldstate_proxy="http://proxy.example:3128"
        )
    )
    assert runtime.world_provider.http.proxy == "http://proxy.example:3128/"
    assert runtime.market_provider.http.proxy is None
    assert runtime.world_provider.http is not runtime.market_provider.http
    await runtime.close()
    assert all(client.closed for client in clients)


def test_worldstate_proxy_rejects_invalid_protocol():
    import pytest
    from pydantic import ValidationError

    from nonebot_plugin_aawarframe.config import Config

    with pytest.raises(ValidationError):
        Config(aawarframe_worldstate_proxy="file:///tmp/proxy")
