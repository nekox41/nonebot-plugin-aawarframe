"""OCR capacity is shared across all adapters by the single Runtime."""
import asyncio
from nonebot_plugin_aawarframe.infrastructure.riven_ocr import MAX_ANALYSES, RivenOCR
import pytest

@pytest.mark.asyncio
async def test_admission_limit_and_recovery():
    ocr = RivenOCR()
    gate = asyncio.Event()
    running = asyncio.Event()

    async def work():
        async with ocr.admission():
            if ocr.pending == MAX_ANALYSES:
                running.set()
            await gate.wait()

    tasks = [asyncio.create_task(work()) for _ in range(MAX_ANALYSES)]
    try:
        await asyncio.wait_for(running.wait(), timeout=2)
        assert ocr.pending == MAX_ANALYSES
        from nonebot_plugin_aawarframe.models.errors import UserInputError
        with pytest.raises(UserInputError):
            async with ocr.admission():
                pass
    finally:
        gate.set()
        await asyncio.gather(*tasks)
    assert ocr.pending == 0
