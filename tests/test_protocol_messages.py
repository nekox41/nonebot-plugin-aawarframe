"""Protocol-independent output and lazy platform conversion."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.onebot.v11 import Message as OBMessage

from nonebot_plugin_aawfcore.protocols.message import (
    Message,
    MessageSegment,
    to_onebot,
)
from nonebot_plugin_aawfcore.protocols.qq import qq_messages, send_reply


def test_neutral_messages_are_not_protocol_objects():
    output = Message(MessageSegment.text("hello"))
    output += MessageSegment.image(b"image-data")
    output += MessageSegment.at("123456789")
    assert not isinstance(output, OBMessage)
    assert output.extract_plain_text() == "hello"
    assert len(output["image"]) == 1
    assert [seg.type for seg in output] == ["text", "image", "at"]


def test_neutral_messages_convert_to_onebot_only_at_send_boundary():
    content = Message([
        MessageSegment.at("12345"),
        MessageSegment.text(" hello"),
        MessageSegment.image(b"picture"),
    ])
    native = to_onebot(content)
    assert isinstance(native, OBMessage)
    assert [segment.type for segment in native] == ["at", "text", "image"]
    assert "[CQ:at,qq=12345]" in str(native)
    assert to_onebot(native) is native


def test_neutral_messages_convert_to_official_qq():
    content = Message([
        MessageSegment.at("openid_member"),
        MessageSegment.text("hello"),
        MessageSegment.image(b"card"),
    ])
    native = qq_messages(content)
    assert len(native) == 1
    assert [segment.type for segment in native[0]] == [
        "mention_user", "text", "file_image"
    ]
    assert native[0][-1].data["content"] == b"card"


@pytest.mark.asyncio
async def test_legacy_send_reply_uses_lazy_native_conversion():
    bot = SimpleNamespace(type="OneBot V11")
    matcher = SimpleNamespace(finish=AsyncMock())
    content = Message(MessageSegment.text("still works"))
    await send_reply(bot, object(), content, matcher)
    arg = matcher.finish.await_args.args[0]
    assert isinstance(arg, OBMessage)
    assert arg.extract_plain_text() == "still works"
