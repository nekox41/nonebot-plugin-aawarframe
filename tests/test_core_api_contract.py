"""Regression tests for the shared HTTP/ASGI response contract."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from nonebot_plugin_aawfcore import api
from nonebot_plugin_aawfcore.protocols.message import Message, MessageSegment


def test_response_segments_keep_order_and_image_payload():
    output = api.pack(Message([
        MessageSegment.text("before"),
        MessageSegment.image(b"image"),
        MessageSegment.text("after"),
    ]))
    assert output["message_type"] == "mixed"
    assert [segment["type"] for segment in output["segments"]] == [
        "text", "image", "text",
    ]
    assert base64.b64decode(output["segments"][1]["data_base64"]) == b"image"
    assert api.pack(Message(MessageSegment.text("ok")))["message_type"] == "text"
    assert api.pack(Message(MessageSegment.image(b"image")))["message_type"] == "image"


@pytest.mark.asyncio
async def test_query_serializes_output_and_validates_base64(monkeypatch):
    runtime = SimpleNamespace(control=SimpleNamespace(
        settings=SimpleNamespace(commands=[SimpleNamespace(feature="help")]),
    ))
    dispatch = AsyncMock(return_value=Message(MessageSegment.text("ok")))
    monkeypatch.setattr(api, "get_runtime", lambda: runtime)
    monkeypatch.setattr(api, "dispatch", dispatch)
    payload = {"feature": "help", "arguments": "", "bot_id": "bot",
               "group_id": "group", "user_id": "user"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://internal"
    ) as client:
        response = await client.post("/v1/query", json=payload)
        assert response.status_code == 200
        assert response.json() == {
            "message_type": "text", "segments": [{"type": "text", "text": "ok"}]
        }
        dispatch.assert_awaited_once_with(
            "help", "", None, subscriber=("bot", "group", "user"),
        )
        response = await client.post("/v1/query", json={
            **payload, "image_base64": "invalid!",
        })
        assert response.status_code == 400
        assert dispatch.await_count == 1
        response = await client.post("/v1/query", json={
            **payload,
            "image_base64": "A" * ((api.MAX_IMAGE_BYTES + 2) // 3 * 4 + 32),
        })
        assert response.status_code == 413
        assert dispatch.await_count == 1
