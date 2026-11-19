"""真实 QQ 官方事件与协议前端收发（核心 API 独立）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("nonebot.adapters.qq")
import nonebot

assert (nonebot.get_plugin("nonebot_plugin_aawfqq") or nonebot.load_plugin("nonebot_plugin_aawfqq")) is not None

from nonebot.adapters.qq import GroupMessageCreateEvent, Message, MessageSegment
from nonebot_plugin_aawfcore.api import pack
from nonebot_plugin_aawfcore.protocols.message import Message as CoreMessage
from nonebot_plugin_aawfcore.protocols.message import MessageSegment as CoreSegment
from nonebot_plugin_aawfqq import router


GROUP = "g_openid-example_1234"
MEMBER = "m_openid-example_4567"


def make_bot():
    return SimpleNamespace(
        self_id="app-id", type="QQ",
        send=AsyncMock(), send_to_group=AsyncMock(), send_to_channel=AsyncMock(),
    )


def test_real_group_event_uses_openid_not_numeric_qq():
    event = GroupMessageCreateEvent.model_validate({
        "id": "official-message-id",
        "content": "订阅 夜灵",
        "timestamp": "2026-11-19T09:00:00+08:00",
        "author": {
            "id": "author", "username": "player", "bot": False,
            "member_openid": MEMBER, "member_role": "member",
        },
        "group_id": "legacy-group-id", "group_openid": GROUP,
        "message_type": 0, "mentions": [], "attachments": [],
    })
    assert router.session(make_bot(), event) == (
        "app-id", "qq-group:" + GROUP, MEMBER
    )
    assert event.get_plaintext() == "订阅 夜灵"


def test_official_pagination_and_typed_segments():
    payload = pack(CoreMessage([
        CoreSegment.text("卡片"),
        CoreSegment.image(b"image1"),
        CoreSegment.image(b"image2"),
        CoreSegment.at(MEMBER),
    ]))["segments"]
    result = router.pages(payload)
    assert len(result) == 2
    assert [seg.type for seg in result[0]] == ["text", "file_image"]
    assert [seg.type for seg in result[1]] == ["file_image", "mention_user"]
    assert result[0][-1].data["content"] == b"image1"


@pytest.mark.asyncio
async def test_group_and_channel_subscriptions_sent_via_official_api():
    bot = make_bot()
    payload = pack(CoreMessage([
        CoreSegment.at(MEMBER),
        CoreSegment.text("已到时间"),
    ]))["segments"]
    await router.deliver(bot, {
        "group_id": "qq-group:" + GROUP, "segments": payload,
    })
    assert bot.send_to_group.await_args.kwargs["group_openid"] == GROUP
    assert [seg.type for seg in bot.send_to_group.await_args.kwargs["message"]] == [
        "mention_user", "text"
    ]
    await router.deliver(bot, {
        "group_id": "qq-channel:chan123", "segments": payload,
    })
    assert bot.send_to_channel.await_args.kwargs["channel_id"] == "chan123"
    bot.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_official_image_receive_and_quoted_image(monkeypatch):
    monkeypatch.setattr(router, "download_image", AsyncMock(return_value=b"picture"))
    image = MessageSegment.image("https://gchat.qpic.cn/myimage")
    event = SimpleNamespace(
        get_message=lambda: Message([image]),
        get_reply_message=lambda: None,
    )
    assert await router.event_image(event) == b"picture"
    quoted = SimpleNamespace(
        get_message=lambda: Message(MessageSegment.text("分析")),
        get_reply_message=lambda: Message([image]),
    )
    assert await router.event_image(quoted) == b"picture"
    assert router.download_image.await_count == 2
