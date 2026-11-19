"""OneBot V11 引用消息/图片地址读取；仅负责协议媒体 IO。"""

import logging

import httpx
from nonebot.adapters.onebot.v11 import Message

from nonebot_plugin_aawfqq.media import decode_inline, download_image

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
