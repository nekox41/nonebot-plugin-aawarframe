"""供各协议包调用的 HTTP API 客户端。

默认 ASGITransport（进程内 HTTP，无 TCP 监听/令牌泄漏）；协议间统一 JSON
消息格式。未来远程部署时可替换为带鉴权的真实 HTTP transport。
"""

import asyncio
from contextlib import asynccontextmanager

import httpx

from .api import app


class CoreClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://aawfcore.internal",
            timeout=httpx.Timeout(60.0),
        )

    async def call(self, endpoint: str, data: dict) -> dict:
        result = await self._client.post(endpoint, json=data)
        result.raise_for_status()
        return result.json()

    async def route(self, **payload) -> dict:
        return await self.call("/v1/route", payload)

    async def query(self, **payload) -> dict:
        return await self.call("/v1/query", payload)

    async def claim(self, bot_ids: list[str], protocol: str) -> list[dict]:
        result = await self.call("/v1/notifications/claim", {
            "bot_ids": bot_ids, "protocol": protocol,
        })
        return result["deliveries"]

    async def ack(self, delivery_id: int, *, ok: bool, error: str = ""):
        await self.call(
            f"/v1/notifications/{delivery_id}/ack",
            {"ok": ok, "error": error[:200]},
        )

    @asynccontextmanager
    async def ocr_admission(self):
        # One in-process Core runtime: both QQ and OneBot share the same quota.
        from .bootstrap import get_runtime

        from .models.errors import UserInputError

        try:
            async with get_runtime().ocr.admission():
                yield
        except UserInputError as exc:
            # The protocol layer should show a user-readable capacity error.
            raise ValueError(str(exc)) from None

    @asynccontextmanager
    async def ocr_download(self):
        from .bootstrap import get_runtime
        from .infrastructure.riven_ocr import DOWNLOAD_TIMEOUT

        ocr = get_runtime().ocr
        try:
            async with asyncio.timeout(DOWNLOAD_TIMEOUT):
                async with ocr.download_slots:
                    yield
        except TimeoutError:
            raise ValueError('图片下载超时，请稍后重试。') from None

    async def close(self):
        await self._client.aclose()


def decode_image(segment: dict) -> bytes:
    import base64

    return base64.b64decode(segment["data_base64"], validate=True)
