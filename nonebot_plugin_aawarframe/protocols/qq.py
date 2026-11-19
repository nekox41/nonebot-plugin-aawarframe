"""QQ 官方机器人适配：OpenID 范围、官方消息段及图片接收。

输入：现有查询层产生的 OneBot 风格内部 Message（作为过渡型消息载体）。
输出：官方 QQ MessageSegment / bot.send 或 bot.send_to_group。
OneBot 并不需要在线连接；发送操作始终调用当前 QQ 官方 bot。
"""

import base64
import logging
from urllib.parse import urlsplit

import httpx

from ..models.errors import UserInputError

logger = logging.getLogger(__name__)
GROUP_PREFIX = "qq-group:"
CHANNEL_PREFIX = "qq-channel:"


def is_qq_bot(bot) -> bool:
    """QQ 适配器 Bot 类型为 QQ，OneBot V11 类型为 OneBot V11。"""
    return getattr(bot, "type", None) == "QQ"


def group_scope(bot, event) -> tuple[str, str, str] | None:
    """订阅隔离到应用、场景、OpenID，不能混用数字 QQ 群号或 C2C OpenID。"""
    if is_qq_bot(bot):
        if group_openid := getattr(event, "group_openid", None):
            return str(bot.self_id), GROUP_PREFIX + str(group_openid), event.get_user_id()
        # QQ 频道消息也可用于订阅，按频道单独隔离。
        if getattr(event, "channel_id", None) and getattr(event, "guild_id", None):
            return (
                str(bot.self_id),
                CHANNEL_PREFIX + str(event.channel_id),
                event.get_user_id(),
            )
        return None
    if hasattr(event, "group_id"):
        return (
            str(bot.self_id), str(event.group_id),
            str(getattr(event, "user_id", event.get_user_id())),
        )
    return None


def command_identity(bot, event) -> tuple[str, str | None]:
    scope = group_scope(bot, event)
    return event.get_user_id(), scope[1] if scope else None


def _image_segment_to_qq(segment, qq_seg):
    file = segment.data.get("file") or segment.data.get("url", "")
    if isinstance(file, bytes):
        return qq_seg.file_image(file)
    if not isinstance(file, str):
        raise UserInputError("图片格式不受 QQ 官方接口支持。")
    if file.startswith("base64://"):
        try:
            content = base64.b64decode(file[len("base64://"):], validate=True)
        except (ValueError, base64.binascii.Error):
            raise UserInputError("图片编码错误，无法发送。") from None
        return qq_seg.file_image(content)
    url = urlsplit(file)
    if url.scheme in ("https", "http") and url.netloc:
        return qq_seg.image(file)
    raise UserInputError("图片不是可发送的二进制数据或 URL。")


def qq_messages(message):
    """把内部文字/图片转换为官方 QQ 消息。

    QQ 群 API 一次仅接收一份媒体文件。多张卡片拆成多条消息，
    不会在 QQ Adapter 的 _extract_qq_media 中丢掉前几张图片。
    """
    from nonebot.adapters.qq import Message as QQMessage
    from nonebot.adapters.qq import MessageSegment as QQSegment

    results = []
    current = QQMessage()
    media_in_current = False
    for segment in message:
        if segment.type == "image":
            if media_in_current:
                results.append(current)
                current = QQMessage()
            current += _image_segment_to_qq(segment, QQSegment)
            media_in_current = True
        elif segment.type == "text":
            current += QQSegment.text(segment.data.get("text", ""))
        elif segment.type == "at":
            current += QQSegment.mention_user(str(segment.data["qq"]))
        elif segment.type == "reply":
            current += QQSegment.reference(str(segment.data["id"]))
        else:
            logger.warning("QQ 官方协议不支持的消息段：%s", segment.type)
    if current:
        results.append(current)
    return results


async def send_reply(bot, event, message, matcher) -> None:
    """普通命令走原 OneBot 输出，QQ 官方命令走 bot.send() 的事件回复。"""
    if not is_qq_bot(bot):
        await matcher.finish(message)
        return

    pages = qq_messages(message)
    try:
        for page in pages:
            await bot.send(event, page)
    except Exception:
        logger.exception("QQ 官方消息发送失败")
        # 图片上传与平台权限独立于查询；不要伪装为查询成功。
        try:
            from nonebot.adapters.qq import MessageSegment as QQSegment

            await bot.send(event, QQSegment.text("查询成功，但图片发送失败，请稍后重试。"))
        except Exception:
            logger.warning("QQ 官方文本回退也失败，可能超出回复窗口", exc_info=True)
    await matcher.finish()


async def send_subscription(bot, delivery, *, image: bytes | None, fallback: str) -> None:
    """发送 QQ 官方机器人订阅提醒。平台拒绝主动推送时向上抛异常供重试。

    官方平台可能限制群主动消息额度/窗口；不使用 OneBot 的 send_group_msg。
    """
    from nonebot.adapters.qq import Message as QQMessage
    from nonebot.adapters.qq import MessageSegment as QQSegment

    target = delivery.group_id
    message = QQMessage()
    if target.startswith(GROUP_PREFIX):
        message += QQSegment.mention_user(delivery.user_id)
    message += QQSegment.text("\n")
    if image is not None:
        message += QQSegment.file_image(image)
    else:
        message += QQSegment.text(fallback)

    if target.startswith(GROUP_PREFIX):
        await bot.send_to_group(group_openid=target[len(GROUP_PREFIX):], message=message)
    elif target.startswith(CHANNEL_PREFIX):
        # 频道使用频道消息 API；不把 QQ 群 OpenID 误传给频道 ID。
        await bot.send_to_channel(channel_id=target[len(CHANNEL_PREFIX):], message=message)
    else:
        raise ValueError("非法的 QQ 官方订阅会话类型")


async def message_image(bot, event, http):
    """官方 QQ 附件图片读取；引用回复使用适配器已解出的 reply，而非 OneBot get_msg。"""
    from ..infrastructure.riven_ocr import LIMIT, download_image

    message = event.get_message()
    images = [seg for seg in message if seg.type == "image"]
    if not images:
        reply = getattr(event, "get_reply_message", None)
        quoted = reply() if callable(reply) else None
        if quoted is None:
            quoted_data = getattr(event, "reply", None)
            if quoted_data is not None:
                from nonebot.adapters.qq import Message as QQMessage
                quoted = QQMessage.from_qq_message(quoted_data)
        if quoted is not None:
            images = [seg for seg in quoted if seg.type == "image"]
    if len(images) != 1:
        raise UserInputError("请在“分析”后附上一张紫卡图片，或引用一张图片。")
    url = images[0].data.get("url", "")
    if not isinstance(url, str):
        raise UserInputError("图片地址无效，请重新上传。")
    try:
        data = await download_image(url, http)
    except httpx.HTTPError:
        data = None
    if not data:
        raise UserInputError("无法读取这张图片，请重新上传后分析。")
    if len(data) > LIMIT:
        raise UserInputError("图片超过 12 MB，请裁剪后发送。")
    return data
