"""Issue #1: enforce admission BEFORE QQ image fetch and avoid resource leaks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.infrastructure import riven_ocr
from nonebot_plugin_aawarframe.infrastructure.riven_ocr import (
    LIMIT,
    MAX_ANALYSES,
    MAX_DOWNLOADS,
    RivenOCR,
    download_image,
)
from nonebot_plugin_aawarframe.models.errors import UserInputError


def event_for(index: int):
    # No file field: this path must not invoke get_image before HTTP admission.
    message = Message(MessageSegment("image", {"url": f"https://gchat.qpic.cn/{index}"}))
    return SimpleNamespace(message=message, reply=None, user_id=index)


@pytest.mark.asyncio
async def test_many_users_have_global_limit_before_any_download(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    counters = {"active": 0, "peak": 0, "requests": 0}

    async def serve(request):
        counters["requests"] += 1
        counters["active"] += 1
        counters["peak"] = max(counters["peak"], counters["active"])
        if counters["active"] == MAX_DOWNLOADS:
            started.set()
        try:
            await release.wait()
            return httpx.Response(200, content=b"image")
        finally:
            counters["active"] -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        ocr = RivenOCR()
        runtime = SimpleNamespace(ocr=ocr, http=SimpleNamespace(client=client))
        monkeypatch.setattr(router, "get_runtime", lambda: runtime)
        rendered = Message(MessageSegment.text("OCR done"))
        dispatch = AsyncMock(return_value=rendered)
        monkeypatch.setattr(router, "dispatch", dispatch)
        tasks = [
            asyncio.create_task(router.analyze_riven_message(
                SimpleNamespace(), event_for(i), "", subscriber=None
            ))
            for i in range(MAX_ANALYSES + 5)
        ]
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            await asyncio.sleep(0.02)
            assert ocr.pending == MAX_ANALYSES
            assert counters["active"] <= MAX_DOWNLOADS
            assert counters["peak"] == MAX_DOWNLOADS
            # Five rejected calls never opened a network connection.
            rejected = [t for t in tasks if t.done()]
            assert len(rejected) == 5
            for task in rejected:
                assert isinstance(task.exception(), UserInputError)
                assert "队列已满" in str(task.exception())
        finally:
            release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=3
        )
        assert sum(result == rendered for result in results) == MAX_ANALYSES
        assert sum(isinstance(result, UserInputError) for result in results) == 5
        assert counters["requests"] == MAX_ANALYSES
        assert counters["peak"] == MAX_DOWNLOADS
        assert dispatch.await_count == MAX_ANALYSES
        assert ocr.pending == 0


@pytest.mark.asyncio
async def test_cancellation_releases_admission_and_download_permit(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(request):
        started.set()
        await release.wait()
        return httpx.Response(200, content=b"image")

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        ocr = RivenOCR()
        monkeypatch.setattr(router, "get_runtime", lambda: SimpleNamespace(
            ocr=ocr, http=SimpleNamespace(client=client)
        ))
        monkeypatch.setattr(
            router, "dispatch", AsyncMock(return_value=Message("done"))
        )
        first = asyncio.create_task(
            router.analyze_riven_message(SimpleNamespace(), event_for(1), "")
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            assert ocr.pending == 1
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert ocr.pending == 0
            # A cancelled download has returned its semaphore permit.
            assert ocr.download_slots._value == MAX_DOWNLOADS
            second = asyncio.create_task(
                router.analyze_riven_message(SimpleNamespace(), event_for(2), "")
            )
            await asyncio.sleep(0.02)
            assert ocr.pending == 1
        finally:
            release.set()
        assert await asyncio.wait_for(second, timeout=3) == Message("done")
        assert ocr.pending == 0
        assert ocr.download_slots._value == MAX_DOWNLOADS


@pytest.mark.asyncio
async def test_download_timeout_releases_both_quotas(monkeypatch):
    started = asyncio.Event()

    async def stalled(request):
        started.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled)) as client:
        ocr = RivenOCR()
        monkeypatch.setattr(riven_ocr, "DOWNLOAD_TIMEOUT", 0.025)
        monkeypatch.setattr(router, "get_runtime", lambda: SimpleNamespace(
            ocr=ocr, http=SimpleNamespace(client=client)
        ))
        with pytest.raises(UserInputError, match="下载超时"):
            await router.analyze_riven_message(SimpleNamespace(), event_for(3), "")
        assert started.is_set()
        assert ocr.pending == 0
        assert ocr.download_slots._value == MAX_DOWNLOADS


class Chunks(httpx.AsyncByteStream):
    def __init__(self, n):
        self.n = n
        self.reads = 0

    async def __aiter__(self):
        for _ in range(self.n):
            self.reads += 1
            yield b"x" * 65536

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_content_length_stream_limit_and_qq_redirects():
    paths = []
    large = Chunks(LIMIT // 65536 + 1)

    async def serve(request):
        paths.append(request.url.path)
        if request.url.path == "/oversized-header":
            return httpx.Response(200, content=b"tiny", headers={
                "Content-Length": str(LIMIT + 1)
            })
        if request.url.path == "/lying-header":
            return httpx.Response(
                200, stream=large, headers={"Content-Length": "4"}
            )
        if request.url.path == "/redirect-outside":
            return httpx.Response(302, headers={
                "Location": "https://evil.example.com/secret"
            })
        return httpx.Response(200, content=b"ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        http = SimpleNamespace(client=client)
        with pytest.raises(UserInputError, match="12 MB"):
            await download_image("https://gchat.qpic.cn/oversized-header", http)
        with pytest.raises(UserInputError, match="12 MB"):
            await download_image("https://gchat.qpic.cn/lying-header", http)
        assert large.reads > 1
        assert await download_image(
            "https://gchat.qpic.cn/redirect-outside", http
        ) is None
        assert await download_image("https://evil.example.com/secret", http) is None
        assert await download_image("https://qpic.cn/good", http) == b"ok"
        assert paths == [
            "/oversized-header", "/lying-header", "/redirect-outside", "/good"
        ]


@pytest.mark.asyncio
async def test_nested_recognition_uses_one_admission_and_direct_calls_are_limited():
    ocr = RivenOCR()
    ocr.start = AsyncMock()
    ocr.read = AsyncMock(return_value={"passes": [[{"text": "passed"}]]})
    ocr.process = SimpleNamespace(
        stdin=SimpleNamespace(write=Mock(), drain=AsyncMock())
    )
    async with ocr.admission():
        assert ocr.pending == 1
        assert await ocr.recognize(b"image", lambda rows: rows[0]["text"]) == "passed"
        assert ocr.pending == 1
    assert ocr.pending == 0


@pytest.mark.asyncio
async def test_inherited_context_does_not_let_child_task_bypass_limit():
    ocr = RivenOCR()

    async def check_child():
        async with ocr.admission():
            assert ocr.pending == 2

    async with ocr.admission():
        await asyncio.create_task(check_child())
        assert ocr.pending == 1
    assert ocr.pending == 0
