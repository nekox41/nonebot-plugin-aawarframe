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
        self.entries: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        self.pending: dict[Hashable, asyncio.Task[T]] = {}

    async def get(self, key: Hashable, loader: Callable[[], Awaitable[T]]) -> T:
        cached = self.entries.get(key)
        if cached and self.clock() - cached[0] < self.ttl:
            self.entries.move_to_end(key)
            return cached[1].model_copy(deep=True)
        task = self.pending.get(key)
        if task is None:
            task = asyncio.create_task(self._load(key, loader))
            self.pending[key] = task
            task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        return (await asyncio.shield(task)).model_copy(deep=True)

    async def _load(self, key: Hashable, loader: Callable[[], Awaitable[T]]) -> T:
        try:
            value = await loader()
            if not value.stale:
                self.entries[key] = (self.clock(), value)
                self.entries.move_to_end(key)
                while len(self.entries) > self.max_entries:
                    self.entries.popitem(last=False)
            return value
        except Exception:
            cached = self.entries.get(key)
            if cached and self.clock() - cached[0] <= self.max_age:
                return cached[1].model_copy(update={"stale": True}, deep=True)
            raise
        finally:
            self.pending.pop(key, None)

    async def close(self) -> None:
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.entries.clear()
