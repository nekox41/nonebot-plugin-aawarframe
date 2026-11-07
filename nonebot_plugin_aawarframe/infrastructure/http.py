import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from time import monotonic
from typing import Any

import httpx


class RateLimitError(RuntimeError):
    """上游冷却时间过长，交给缓存或命令层降级。"""


class RateLimiter:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.next_request = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            while self.next_request > monotonic():
                delay = self.next_request - monotonic()
                if delay > 15:
                    raise RateLimitError("上游正在限流冷却，请稍后重试")
                await asyncio.sleep(delay)
            self.next_request = monotonic() + self.interval

    def defer(self, seconds: float) -> None:
        self.next_request = max(self.next_request, monotonic() + seconds)


def retry_after(value: str | None, fallback: float) -> float:
    try:
        seconds = float(value)
        return max(0, seconds) if isfinite(seconds) else fallback
    except (TypeError, ValueError):
        try:
            return max(
                0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            )
        except (TypeError, ValueError, OverflowError):
            return fallback


class HttpClient:
    def __init__(
        self,
        timeout: float = 12,
        *,
        client: httpx.AsyncClient | None = None,
        proxy: str | None = None,
    ):
        self.client = client or httpx.AsyncClient(
            timeout=timeout,
            proxy=proxy,
            headers={
                "User-Agent": "nonebot-plugin-aawarframe/0.6 (+https://github.com/nekox41/nonebot-plugin-aawarframe)"
            },
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        self.market_limiter = RateLimiter()

    async def get_response(
        self, url: str, *, market: bool = False, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        for attempt in range(3):
            if market:
                await self.market_limiter.wait()
            try:
                response = await self.client.get(url, headers=headers)
                if response.status_code == 429:
                    delay = retry_after(response.headers.get("Retry-After"), 2**attempt)
                    if market:
                        self.market_limiter.defer(delay)
                    if delay > 15 or attempt == 2:
                        response.raise_for_status()
                    await asyncio.sleep(delay)
                    continue
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return response
            except httpx.TransportError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)
        raise RuntimeError("请求重试次数已耗尽")

    async def get_json(
        self, url: str, *, market: bool = False, headers: dict[str, str] | None = None
    ) -> Any:
        response = await self.get_response(url, market=market, headers=headers)
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
