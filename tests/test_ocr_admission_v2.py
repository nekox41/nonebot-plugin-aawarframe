"""OCR admission is shared by both protocol frontends and the Core recognizer."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from nonebot_plugin_aawfcore.infrastructure.riven_ocr import (
    MAX_ANALYSES,
    MAX_DOWNLOADS,
    RivenOCR,
)
from nonebot_plugin_aawfcore.models.errors import UserInputError


@pytest.mark.asyncio
async def test_global_admission_rejects_above_eight_before_work():
    ocr = RivenOCR()
    entered = asyncio.Event()
    unblock = asyncio.Event()

    async def request():
        async with ocr.admission():
            entered.set()
            await unblock.wait()

    tasks = [asyncio.create_task(request()) for _ in range(MAX_ANALYSES + 5)]
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        assert ocr.pending == MAX_ANALYSES
        assert sum(task.done() for task in tasks) == 5
        assert sum(
            isinstance(task.exception(), UserInputError)
            for task in tasks if task.done()
        ) == 5
    finally:
        unblock.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(result, UserInputError) for result in results) == 5
    assert ocr.pending == 0


@pytest.mark.asyncio
async def test_cancel_releases_admission_and_download_slot():
    ocr = RivenOCR()
    entered = asyncio.Event()

    async def run():
        async with ocr.admission():
            async with ocr.download_slots:
                entered.set()
                await asyncio.Event().wait()

    task = asyncio.create_task(run())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ocr.pending == 0
    assert ocr.download_slots._value == MAX_DOWNLOADS


@pytest.mark.asyncio
async def test_nested_recognition_uses_same_admission():
    ocr = RivenOCR()
    ocr.start = AsyncMock()
    ocr.read = AsyncMock(return_value={"passes": [[{"text": "ok"}]]})
    ocr.process = SimpleNamespace(stdin=SimpleNamespace(
        write=Mock(), drain=AsyncMock(),
    ))
    async with ocr.admission():
        assert ocr.pending == 1
        assert await ocr.recognize(b"test", lambda rows: rows[0]["text"]) == "ok"
        assert ocr.pending == 1
    assert ocr.pending == 0


@pytest.mark.asyncio
async def test_child_task_cannot_inherit_parent_admission():
    ocr = RivenOCR()

    async def child():
        async with ocr.admission():
            assert ocr.pending == 2

    async with ocr.admission():
        await asyncio.create_task(child())
        assert ocr.pending == 1
    assert ocr.pending == 0
