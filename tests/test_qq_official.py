"""QQ official session and media regression after single-package conversion."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
pytest.importorskip("nonebot.adapters.qq")
from nonebot.adapters.qq import GroupMessageCreateEvent, Message, MessageSegment
from nonebot_plugin_aawfcore.protocols.message import Message as CoreMessage
from nonebot_plugin_aawfcore.protocols.message import MessageSegment as CoreSegment
from nonebot_plugin_aawarframe import router

GROUP = "g_openid-example_1234"
MEMBER = "m_openid-example_4567"

def bot():
    return SimpleNamespace(self_id="app-id", type="QQ", send=AsyncMock(),
                           send_to_group=AsyncMock(), send_to_channel=AsyncMock())

def test_group_event_identity():
    event = GroupMessageCreateEvent.model_validate({
        "id": "official-message-id", "content": "订阅 夜灵",
        "timestamp": "2026-11-19T09:00:00+08:00",
        "author": {"id": "author", "username": "player", "bot": False,
                   "member_openid": MEMBER, "member_role": "member"},
        "group_id": "legacy-group-id", "group_openid": GROUP,
        "message_type": 0, "mentions": [], "attachments": [],
    })
    assert router.session(bot(), event) == ("app-id", "qq-group:" + GROUP, MEMBER)

def test_qq_pagination():
    result = router.convert(CoreMessage([
        CoreSegment.text("卡片"), CoreSegment.image(b"image1"),
        CoreSegment.image(b"image2"), CoreSegment.at(MEMBER),
    ]), "qq")
    assert len(result) == 2
    assert [seg.type for seg in result[0]] == ["text", "file_image"]
    assert [seg.type for seg in result[1]] == ["file_image", "mention_user"]

@pytest.mark.asyncio
async def test_media_and_quote(monkeypatch):
    monkeypatch.setattr("nonebot_plugin_aawarframe.media_qq.download_image", AsyncMock(return_value=b"picture"))
    image = MessageSegment.image("https://gchat.qpic.cn/myimage")
    event = SimpleNamespace(get_message=lambda: Message([image]), get_reply_message=lambda: None)
    assert await router.read_image(bot(), event) == b"picture"
    quoted = SimpleNamespace(get_message=lambda: Message(MessageSegment.text("分析")),
                             get_reply_message=lambda: Message([image]))
    assert await router.read_image(bot(), quoted) == b"picture"
