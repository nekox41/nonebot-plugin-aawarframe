"""Regression: protocol-layer OCR admission precedes any remote image fetch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawfcore.infrastructure.riven_ocr import MAX_ANALYSES, MAX_DOWNLOADS, RivenOCR


@pytest.mark.asyncio
async def test_qq_admission_before_media_fetch(monkeypatch):
    from nonebot_plugin_aawfcore import bootstrap
    from nonebot_plugin_aawfqq import router

    ocr = RivenOCR()
    monkeypatch.setattr(bootstrap, "get_runtime", lambda: SimpleNamespace(ocr=ocr))
    gate = asyncio.Event()
    downloading = asyncio.Event()
    observed = {"in_download": 0, "max_download": 0, "called": 0}

    async def fake_image(event):
        observed["called"] += 1
        observed["in_download"] += 1
        observed["max_download"] = max(observed["max_download"], observed["in_download"])
        if observed["in_download"] == MAX_DOWNLOADS:
            downloading.set()
        try:
            await gate.wait()
            return b"image"
        finally:
            observed["in_download"] -= 1

    monkeypatch.setattr(router, "event_image", fake_image)
    query = AsyncMock(return_value={"segments": [{"type": "text", "text": "ok"}]})
    monkeypatch.setattr(router.client, "query", query)
    bot = SimpleNamespace(self_id="qqapp", send=AsyncMock())
    matcher = SimpleNamespace(finish=AsyncMock())

    async def request(i):
        event = SimpleNamespace(group_openid="group", get_user_id=lambda: str(i))
        state = {"aawf_feature": "riven_analysis", "aawf_arguments": ""}
        await router.accept(bot, event, matcher, state)

    tasks = [asyncio.create_task(request(i)) for i in range(MAX_ANALYSES + 5)]
    try:
        await asyncio.wait_for(downloading.wait(), 2)
        await asyncio.sleep(0.02)
        assert ocr.pending == MAX_ANALYSES
        assert observed["called"] == MAX_DOWNLOADS
        assert observed["max_download"] == MAX_DOWNLOADS
        # The excess five tasks must not acquire network/download resources.
        assert sum(t.done() for t in tasks) == 5
    finally:
        gate.set()
    await asyncio.wait_for(asyncio.gather(*tasks), 2)
    assert ocr.pending == 0
    assert query.await_count == MAX_ANALYSES
    assert observed["called"] == MAX_ANALYSES
    assert bot.send.await_count == MAX_ANALYSES + 5
    assert ocr.download_slots._value == MAX_DOWNLOADS
