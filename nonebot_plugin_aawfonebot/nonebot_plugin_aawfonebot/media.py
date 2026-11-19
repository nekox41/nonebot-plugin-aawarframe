"""OneBot V11 引用消息/图片地址读取；仅负责协议媒体 IO。"""

import base64
import logging
from urllib.parse import urljoin, urlsplit

import httpx
from nonebot.adapters.onebot.v11 import Message

MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_DOMAINS = ("qq.com", "qq.com.cn", "qpic.cn")


async def download_image(url: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=25) as client:
        for _ in range(4):
            parts = urlsplit(url)
            domain = (parts.hostname or "").lower()
            if (
                parts.scheme not in {"http", "https"}
                or not any(domain == item or domain.endswith("." + item) for item in ALLOWED_DOMAINS)
                or parts.username or parts.password
                or parts.port not in {None, 80, 443}
            ):
                return None
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and declared.isdecimal() and int(declared) > MAX_IMAGE_BYTES:
                    raise ValueError("图片超过 12 MB")
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("图片超过 12 MB")
                return bytes(data)
    return None


def decode_inline(value: str) -> bytes | None:
    if not value.startswith("base64://"):
        return None
    encoded = value[len("base64://"):]
    if len(encoded) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 16:
        raise ValueError("图片超过 12 MB")
    image = base64.b64decode(encoded, validate=True)
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 12 MB")
    return image


logger = logging.getLogger(__name__)


def image_segments(message):
    return [item for item in Message(message) if item.type == "image"]


async def message_image(bot, event) -> bytes:
    images = image_segments(event.message)
    if not images:
        reply = getattr(event, "reply", None)
        original = getattr(event, "original_message", event.message)
        reply_id = (
            reply.message_id if reply else next(
                (s.data.get("id") for s in original if s.type == "reply"), None
            )
        )
        if reply_id is not None:
            try:
                data = await bot.get_msg(message_id=int(reply_id))
                images = image_segments(data.get("message") or data.get("raw_message", ""))
            except Exception:
                logger.debug("引用消息读取失败", exc_info=True)
        if not images and reply:
            images = image_segments(reply.message)
    if len(images) != 1:
        raise ValueError("请在“分析”后附上一张紫卡图片，或引用一张图片。")
    image = images[0].data
    urls = []
    if image.get("file") and not image["file"].startswith("base64://"):
        try:
            info = await bot.get_image(file=image["file"])
            if info.get("url"):
                urls.append(info["url"])
        except Exception:
            logger.debug("查询图片地址失败", exc_info=True)
    urls.extend(
        address for address in (image.get("url"), image.get("file"))
        if address and address not in urls
    )
    for address in urls:
        if inline := decode_inline(address):
            return inline
        try:
            if image_data := await download_image(address):
                return image_data
        except httpx.HTTPError:
            continue
    raise ValueError("无法读取图片，请重新上传后分析。")
