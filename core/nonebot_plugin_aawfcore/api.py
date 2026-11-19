"""AAWarframe 核心内部 HTTP/ASGI API。

不暴露公网端口。协议插件通过 httpx.ASGITransport 调用这些端点；
核心不 import QQ/OneBot 类、也不处理平台消息事件。
"""

import base64
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .bootstrap import get_runtime
from .commands.router import dispatch
from .models.errors import UserInputError

logger = logging.getLogger(__name__)
app = FastAPI(title="AAWarframe Core API", version="1", docs_url=None, redoc_url=None)
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class RouteRequest(BaseModel):
    text: str = Field(max_length=4000)
    starts: list[str] = Field(default_factory=lambda: ["/", ""])
    user_id: str = Field(max_length=180)
    group_id: str | None = Field(default=None, max_length=240)


class QueryRequest(BaseModel):
    feature: str = Field(max_length=80)
    arguments: str = Field(default="", max_length=4000)
    bot_id: str = Field(max_length=180)
    user_id: str = Field(max_length=180)
    group_id: str | None = Field(default=None, max_length=240)
    image_base64: str | None = None


class ClaimsRequest(BaseModel):
    bot_ids: list[str] = Field(max_length=40)
    protocol: Literal["qq", "onebot"]


class AckRequest(BaseModel):
    ok: bool
    error: str = Field(default="", max_length=200)


def pack(message) -> dict:
    """标准消息协议：message_type + 按顺序排列的 text/image/at/reply 段。"""
    segments = []
    for item in message:
        kind = item.type
        if kind == "text":
            segments.append({"type": "text", "text": item.data["text"]})
        elif kind == "image":
            value = item.data.get("file")
            if isinstance(value, bytes):
                payload = base64.b64encode(value).decode("ascii")
            elif isinstance(value, str) and value.startswith("base64://"):
                payload = value[len("base64://"):]
            else:
                raise ValueError("核心只允许返回二进制或 Base64 图片，不接受本地路径")
            segments.append({"type": "image", "data_base64": payload})
        elif kind == "at":
            segments.append({"type": "at", "user_id": str(item.data["qq"])})
        elif kind == "reply":
            segments.append({"type": "reply", "message_id": str(item.data["id"])})
        else:
            raise ValueError(f"未知核心消息类型：{kind}")
    types = {segment["type"] for segment in segments}
    message_type = (
        "image" if types == {"image"} else "text" if types == {"text"}
        else "mixed" if segments else "none"
    )
    return {"message_type": message_type, "segments": segments}


@app.post("/v1/route")
async def route(payload: RouteRequest):
    runtime = get_runtime()
    parsed = runtime.control.route(
        payload.text.lstrip(), set(payload.starts), payload.user_id, payload.group_id,
    )
    if parsed is None:
        return {"matched": False}
    feature, arguments = parsed
    return {"matched": True, "feature": feature, "arguments": arguments}


@app.post("/v1/query")
async def query(payload: QueryRequest):
    if payload.feature not in {cmd.feature for cmd in get_runtime().control.settings.commands}:
        raise HTTPException(400, detail="未知查询功能")
    image = None
    if payload.image_base64 is not None:
        if len(payload.image_base64) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 16:
            raise HTTPException(413, detail="图片超过 12 MB")
        try:
            image = base64.b64decode(payload.image_base64, validate=True)
        except ValueError:
            raise HTTPException(400, detail="图片编码无效") from None
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail="图片超过 12 MB")
    scope = (
        (payload.bot_id, payload.group_id, payload.user_id)
        if payload.group_id is not None else None
    )
    message = await dispatch(payload.feature, payload.arguments, image, subscriber=scope)
    return pack(message)


@app.post("/v1/notifications/claim")
async def claim(payload: ClaimsRequest):
    runtime = get_runtime()
    service = runtime.subscriptions
    now = datetime.now(timezone.utc)
    # 仅取本协议当前在线 bot 的通知。消息发送权完全留在协议插件。
    deliveries = service.store.claim_due(
        now, set(payload.bot_ids), protocol=payload.protocol
    )
    result = []
    for delivery in deliveries:
        try:
            message = await service.prepare_delivery(delivery, now)
            result.append({
                "id": delivery.id,
                "bot_id": delivery.bot_id,
                "group_id": delivery.group_id,
                "user_id": delivery.user_id,
                "attempts": delivery.attempts,
                **pack(message),
            })
        except Exception as exc:
            logger.exception("订阅通知格式化失败：%s", delivery.id)
            service.store.mark_failed(delivery.id, delivery.attempts, now, type(exc).__name__)
    return {"deliveries": result}


@app.post("/v1/notifications/{delivery_id}/ack")
async def acknowledge(delivery_id: int, payload: AckRequest):
    service = get_runtime().subscriptions
    now = datetime.now(timezone.utc)
    if payload.ok:
        service.store.mark_sent(delivery_id, now)
    else:
        service.store.mark_failed(
            delivery_id, service.store.delivery_attempts(delivery_id), now,
            payload.error or "platform_send_failed",
        )
    return {"ok": True}
