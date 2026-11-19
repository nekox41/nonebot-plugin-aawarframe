# 作用：实现 infrastructure 层的 cache 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from time import monotonic
from typing import Generic, TypeVar

from ..models.common import Snapshot

T = TypeVar("T", bound=Snapshot)


class AsyncTTLCache(Generic[T]):
    """同键请求合并；失败只在限定年龄内回退，调用者取消不影响其他等待者。"""

    def __init__(
        self,
        ttl: float,
        max_age: float,
        *,
        max_entries: int = 256,
        clock: Callable[[], float] = monotonic,
    ):
        self.ttl = ttl
        self.max_age = max_age
        self.max_entries = max_entries
        self.clock = clock
        self.entries: OrderedDict[Hashable, tuple[float, float, T]] = OrderedDict()
        self.pending: dict[Hashable, asyncio.Task[T]] = {}
        self.hits = 0
        self.misses = 0
        self.coalesced = 0
        self.loads = 0

    async def get(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        *,
        ttl: float | Callable[[], float] | None = None,
    ) -> T:
        now = self.clock()
        cached = self.entries.get(key)
        if cached and now < cached[1]:
            self.hits += 1
            self.entries.move_to_end(key)
            return cached[2].model_copy(deep=True)

        self.misses += 1
        task = self.pending.get(key)
        if task is None:
            task = asyncio.create_task(self._load(key, loader, ttl))
            self.pending[key] = task
            task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        else:
            self.coalesced += 1
        return (await asyncio.shield(task)).model_copy(deep=True)

    async def _load(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        ttl: float | Callable[[], float] | None,
    ) -> T:
        try:
            self.loads += 1
            value = await loader()
            effective_ttl = self.ttl if ttl is None else ttl() if callable(ttl) else ttl
            effective_ttl = min(self.ttl, max(0.0, effective_ttl))
            if not value.stale and effective_ttl > 0:
                stored_at = self.clock()
                self.entries[key] = (stored_at, stored_at + effective_ttl, value)
                self.entries.move_to_end(key)
                while len(self.entries) > self.max_entries:
                    self.entries.popitem(last=False)
            return value
        except Exception:
            cached = self.entries.get(key)
            if cached and self.clock() - cached[0] <= self.max_age:
                return cached[2].model_copy(update={"stale": True}, deep=True)
            raise
        finally:
            self.pending.pop(key, None)

    async def close(self) -> None:
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.entries.clear()
