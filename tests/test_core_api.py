"""Core JSON/HTTP API, message envelope and protocol-only outbound adapters."""

import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from nonebot_plugin_aawarframe import api
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.protocols.message import Message, MessageSegment


@pytest.mark.asyncio
async def test_route_and_query_are_protocol_independent(monkeypatch):
    core = SimpleNamespace(
        control=SimpleNamespace(
            route=Mock(return_value=("riven_analysis", "紫卡")),
            settings=SimpleNamespace(commands=[SimpleNamespace(feature="riven_analysis")]),
        )
    )
    monkeypatch.setattr(api, "get_runtime", lambda: core)
    captured = {}

    async def query(feature, arguments, image, *, subscriber):
        captured.update(
            feature=feature, arguments=arguments,
            image=image, subscriber=subscriber,
        )
        return Message([
            MessageSegment.text("图片已识别"),
            MessageSegment.image(b"RIFF-WEBP-image"),
        ])

    monkeypatch.setattr(api, "dispatch", query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app),
        base_url="http://aawfcore.internal",
    ) as client:
        result = await client.post("/v1/route", json={
            "text": "分析 紫卡", "starts": ["/", ""],
            "user_id": "OPENID_user", "group_id": "qq-group:groupid",
        })
        assert result.status_code == 200
        assert result.json() == {
            "matched": True, "feature": "riven_analysis", "arguments": "紫卡"
        }
        data = await client.post("/v1/query", json={
            "feature": "riven_analysis",
            "arguments": "紫卡",
            "bot_id": "app-id", "user_id": "OPENID_user",
            "group_id": "qq-group:groupid",
            "image_base64": base64.b64encode(b"card").decode(),
        })
        assert data.status_code == 200
        payload = data.json()
        assert payload["message_type"] == "mixed"
        assert payload["segments"][0] == {"type": "text", "text": "图片已识别"}
        assert base64.b64decode(payload["segments"][1]["data_base64"]) == b"RIFF-WEBP-image"
    assert captured == {
        "feature": "riven_analysis", "arguments": "紫卡",
        "image": b"card", "subscriber": ("app-id", "qq-group:groupid", "OPENID_user"),
    }


@pytest.mark.asyncio
async def test_query_rejects_unsupported_feature_and_large_images(monkeypatch):
    core = SimpleNamespace(control=SimpleNamespace(
        settings=SimpleNamespace(commands=[SimpleNamespace(feature="riven_analysis")])
    ))
    monkeypatch.setattr(api, "get_runtime", lambda: core)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app),
        base_url="http://aawfcore.internal",
    ) as client:
        data = {
            "bot_id": "app-id", "user_id": "OPENID_user", "group_id": "qq-group:g",
            "feature": "not-a-real-command",
        }
        assert (await client.post("/v1/query", json=data)).status_code == 400
        data["feature"] = "riven_analysis"
        data["image_base64"] = base64.b64encode(b"x" * (12 * 1024 * 1024 + 1)).decode()
        assert (await client.post("/v1/query", json=data)).status_code == 413


@pytest.mark.asyncio
async def test_claim_delivery_and_ack_via_backend_http(monkeypatch):
    delivery = SimpleNamespace(
        id=32, bot_id="app", group_id="qq-group:gid",
        user_id="openid", attempts=1,
    )
    store = SimpleNamespace(
        claim_due=Mock(return_value=[delivery]),
        mark_sent=Mock(), mark_failed=Mock(),
        delivery_attempts=Mock(return_value=2),
    )
    service = SimpleNamespace(
        store=store,
        prepare_delivery=AsyncMock(return_value=Message([
            MessageSegment.at("openid"),
            MessageSegment.image(b"png"),
        ])),
    )
    monkeypatch.setattr(api, "get_runtime", lambda: SimpleNamespace(subscriptions=service))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app),
        base_url="http://aawfcore.internal",
    ) as client:
        response = await client.post("/v1/notifications/claim", json={
            "bot_ids": ["app"], "protocol": "qq",
        })
        assert response.status_code == 200
        items = response.json()["deliveries"]
        assert len(items) == 1
        assert items[0]["group_id"] == "qq-group:gid"
        assert [s["type"] for s in items[0]["segments"]] == ["at", "image"]
        assert (await client.post(
            "/v1/notifications/32/ack", json={"ok": False, "error": "platform_rate_limit"}
        )).status_code == 200
        store.mark_failed.assert_called_once()
        assert (await client.post(
            "/v1/notifications/32/ack", json={"ok": True}
        )).status_code == 200
        store.mark_sent.assert_called_once()
    assert store.claim_due.call_args.kwargs["protocol"] == "qq"


@pytest.mark.asyncio
async def test_unified_adapter_conversion_without_http_roundtrip(monkeypatch):
    import nonebot
    assert (nonebot.get_plugin("nonebot_plugin_aawarframe") or
            nonebot.load_plugin("nonebot_plugin_aawarframe")) is not None
    from nonebot_plugin_aawarframe.router import convert

    message = Message([
        MessageSegment.text("收到"),
        MessageSegment.image(b"webp"),
        MessageSegment.at("123"),
    ])
    qq = convert(message, "qq")
    onebot = convert(message, "onebot")
    assert [s.type for s in qq[0]] == ["text", "file_image", "mention_user"]
    assert [s.type for s in onebot[0]] == ["text", "image", "at"]
