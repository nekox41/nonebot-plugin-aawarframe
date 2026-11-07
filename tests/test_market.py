import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from nonebot_plugin_aawarframe.commands.parsing import parse_market_query
from nonebot_plugin_aawarframe.infrastructure.http import HttpClient, RateLimiter, retry_after
from nonebot_plugin_aawarframe.localization.resolver import ItemResolver
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.models.market import Item, MarketQuery, Order
from nonebot_plugin_aawarframe.providers.market import MarketProvider
from nonebot_plugin_aawarframe.services.market import MarketService


def make_order(**updates):
    data = dict(
        id="o1",
        type="sell",
        platinum=5,
        quantity=6,
        perTrade=2,
        visible=True,
        rank=0,
        updatedAt="2026-11-06T00:00:00Z",
        user={"ingameName": "卖家", "status": "online", "platform": "pc", "crossplay": True},
    )
    data.update(updates)
    return Order.model_validate(data)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "满级",
        "foo --oops yes",
        "foo --rank -1",
        "foo --rank",
        "foo --rank 0 --rank 1",
        "满级 foo --rank 0",
        '"unclosed',
    ],
)
def test_invalid_arguments(text):
    with pytest.raises(UserInputError):
        parse_market_query(text)


def test_names_with_spaces_and_rank():
    query = parse_market_query("满级 Frost Prime --subtype blueprint")
    assert query.name == "Frost Prime" and query.max_rank
    assert parse_market_query("Frost Prime Set --rank 0").rank == 0


def test_resolution_is_normalized_and_nearest(market_items):
    resolver = ItemResolver([Item.model_validate(item) for item in market_items])
    assert resolver.resolve("Frost Prime Set") == "frost_prime_set"
    assert resolver.resolve("膛线") == "serration"
    assert resolver.resolve("serraton") == "serration"
    assert resolver.resolve("totally unknown item with no match") is None


async def test_market_empty_orders_do_not_crash(market_items):
    item = Item.model_validate(market_items[0])
    provider = SimpleNamespace(
        catalog=AsyncMock(return_value=Snapshot(data=[item], source="catalog")),
        item=AsyncMock(return_value=Snapshot(data=item, source="item")),
        orders=AsyncMock(return_value=Snapshot(data=[], source="orders")),
    )
    result = await MarketService(provider).query(MarketQuery(name="膛线"))
    assert result.status == DataStatus.EMPTY
    assert "暂无符合" in result.text() and "成交统计暂不可用" in result.text()


async def test_market_rank_status_sort_and_quantity(market_items):
    item = Item.model_validate(market_items[0])
    orders = [
        make_order(id="expensive", platinum=10, rank=10),
        make_order(id="cheap", rank=10),
        make_order(id="base", rank=0),
        make_order(id="hidden", rank=10, visible=False),
        make_order(id="buy", type="buy", rank=10, platinum=3),
        make_order(
            id="offline",
            rank=10,
            user={"ingameName": "离线", "status": "offline", "platform": "pc"},
        ),
    ]
    provider = SimpleNamespace(
        catalog=AsyncMock(return_value=Snapshot(data=[item], source="catalog")),
        item=AsyncMock(return_value=Snapshot(data=item, source="item")),
        orders=AsyncMock(return_value=Snapshot(data=orders, source="orders", stale=True)),
    )
    result = await MarketService(provider).query(MarketQuery(name="膛线", max_rank=True))
    assert result.stale
    assert [row[1] for row in result.sections[0].rows] == ["5", "10"]
    assert result.sections[0].rows[0][2] == "2 件 / 10 白金"
    assert next(s for s in result.sections if s.title.startswith("买单")).rows[0][1] == "3"
    assert "/w 卖家" in result.text()
    assert provider.orders.call_args.args[1].rank == 10


async def test_unranked_item_rejects_max_rank(market_items):
    item = Item.model_validate(market_items[1])
    provider = SimpleNamespace(
        catalog=AsyncMock(return_value=Snapshot(data=[item], source="catalog")),
        item=AsyncMock(return_value=Snapshot(data=item, source="item")),
    )
    with pytest.raises(UserInputError, match="不存在等级"):
        await MarketService(provider).query(MarketQuery(name="Frost Prime Set", max_rank=True))


async def test_provider_headers_versioning_and_cache_keys(market_items, tmp_path):
    paths = []

    def handle(request):
        paths.append(request.url.path)
        assert request.headers["Language"] == "zh-hans"
        assert request.headers["Platform"] == "pc"
        assert request.headers["Crossplay"] == "true"
        assert "aawarframe" in request.headers["User-Agent"]
        if request.url.path.endswith("/versions"):
            data = {"collections": {"items": "v1"}}
        elif request.url.path.endswith("/items"):
            data = market_items
        else:
            data = []
        return httpx.Response(200, json={"data": data, "error": None})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), headers={"User-Agent": "aawarframe-test"}
    )
    http = HttpClient(client=client)
    http.market_limiter.interval = 0
    provider = MarketProvider(http, tmp_path)
    await provider.catalog()
    assert (tmp_path / "market-items.json").exists()
    await provider.catalog_cache.close()
    await provider.catalog()
    assert paths.count("/v2/items") == 1
    base = MarketQuery(name="膛线", rank=0)
    await asyncio.gather(*(provider.orders("serration", base) for _ in range(10)))
    await provider.orders("serration", base.model_copy(update={"rank": 10}))
    await provider.orders("serration", base.model_copy(update={"subtype": "blueprint"}))
    assert paths.count("/v2/orders/item/serration") == 3
    assert not any("v1" in path for path in paths)
    await provider.close()
    await http.close()


async def test_429_retries_and_long_retry_after_is_not_ignored(monkeypatch):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("nonebot_plugin_aawarframe.infrastructure.http.asyncio.sleep", sleep)
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    http = HttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    assert await http.get_json("https://fixture.test") == {"ok": True}
    assert sleeps == [2]
    await http.close()

    def limited(request):
        return httpx.Response(429, headers={"Retry-After": "120"})

    http = HttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(limited)))
    with pytest.raises(httpx.HTTPStatusError):
        await http.get_json("https://fixture.test", market=True)
    assert http.market_limiter.next_request > 0
    from nonebot_plugin_aawarframe.infrastructure.http import RateLimitError

    with pytest.raises(RateLimitError):
        await http.get_json("https://fixture.test", market=True)
    await http.close()


def test_retry_after_http_date():
    assert retry_after("garbage", 3) == 3
    assert retry_after("-1", 3) == 0
    assert retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 3) == 0


async def test_rate_limit_spacing():
    limiter = RateLimiter(0.02)
    loop = asyncio.get_running_loop()
    times = []

    async def request():
        await limiter.wait()
        times.append(loop.time())

    await asyncio.gather(*(request() for _ in range(3)))
    assert all(b - a >= 0.018 for a, b in zip(times, times[1:]))


async def test_timeout_and_5xx_have_bounded_retries(monkeypatch):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("nonebot_plugin_aawarframe.infrastructure.http.asyncio.sleep", sleep)
    attempts = 0

    def failed(request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout", request=request)

    http = HttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(failed)))
    with pytest.raises(httpx.ReadTimeout):
        await http.get_json("https://fixture.test")
    assert attempts == 3 and sleeps == [1, 2]
    await http.close()

    attempts = 0
    sleeps.clear()

    def failed_server(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    http = HttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(failed_server)))
    with pytest.raises(httpx.HTTPStatusError):
        await http.get_json("https://fixture.test")
    assert attempts == 3 and sleeps == [1, 2]
    await http.close()


async def test_corrupt_catalogue_and_expired_persisted_fallback(market_items, tmp_path):
    from datetime import timedelta

    from nonebot_plugin_aawarframe.infrastructure.storage import write_json
    from nonebot_plugin_aawarframe.models.common import utcnow

    http = SimpleNamespace(get_json=AsyncMock(side_effect=OSError("offline")))
    provider = MarketProvider(http, tmp_path)
    await write_json(
        provider.catalog_path,
        {
            "version": "v1",
            "items": market_items,
            "fetched_at": (utcnow() - timedelta(hours=2)).isoformat(),
        },
    )
    result = await provider.catalog()
    assert result.stale and result.data[0].slug == "serration"
    await write_json(
        provider.catalog_path,
        {
            "version": "v1",
            "items": market_items,
            "fetched_at": (utcnow() - timedelta(days=2)).isoformat(),
        },
    )
    with pytest.raises(OSError):
        await provider.catalog()
    provider.catalog_path.write_text("{corrupted")
    with pytest.raises(OSError):
        await provider.catalog()
    await provider.close()
