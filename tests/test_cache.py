# 作用：验证 cache 相关行为。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio

import pytest

from nonebot_plugin_aawarframe.infrastructure.cache import AsyncTTLCache
from nonebot_plugin_aawarframe.models.common import Snapshot


async def test_concurrent_requests_share_result_and_copy():
    cache = AsyncTTLCache(45, 180)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return Snapshot(data={"count": 1}, source="fixture")

    results = await asyncio.gather(*(cache.get("pc", load) for _ in range(20)))
    assert calls == 1
    results[0].data["count"] = 999
    assert (await cache.get("pc", load)).data["count"] == 1
    await cache.close()


async def test_stale_expiry_does_not_reset_age():
    time = [0.0]
    cache = AsyncTTLCache(45, 180, clock=lambda: time[0])

    async def load():
        return Snapshot(data=[], source="fixture")

    async def fail():
        raise OSError("upstream down")

    initial = await cache.get("pc", load)
    time[0] = 46
    result = await cache.get("pc", fail)
    assert result.stale and result.fetched_at == initial.fetched_at
    time[0] = 181
    with pytest.raises(OSError):
        await cache.get("pc", fail)
    await cache.close()


async def test_waiter_cancellation_does_not_cancel_shared_load():
    cache = AsyncTTLCache(45, 180)
    ready = asyncio.Event()

    async def load():
        await ready.wait()
        return Snapshot(data=1, source="fixture")

    first = asyncio.create_task(cache.get("key", load))
    second = asyncio.create_task(cache.get("key", load))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    ready.set()
    assert (await second).data == 1
    await cache.close()


async def test_stale_loader_result_never_resets_cache_age():
    time = [0.0]
    cache = AsyncTTLCache(1, 3, clock=lambda: time[0])

    async def fresh():
        return Snapshot(data=1, source="fixture")

    async def stale():
        return Snapshot(data=2, source="fixture", stale=True)

    async def fail():
        raise OSError("offline")

    await cache.get("pc", fresh)
    time[0] = 2
    assert (await cache.get("pc", stale)).stale
    time[0] = 4
    with pytest.raises(OSError):
        await cache.get("pc", fail)
    await cache.close()


async def test_shutdown_cancels_inflight_loads():
    cache = AsyncTTLCache(30, 90)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def load():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    waiter = asyncio.create_task(cache.get("key", load))
    await started.wait()
    await cache.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert cancelled.is_set()
    assert not cache.pending
