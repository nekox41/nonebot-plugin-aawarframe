"""同一个核心消息载体可以被 QQ 官方和 OneBot 两个平台转换。"""

import base64

from nonebot_plugin_aawfcore.api import pack
from nonebot_plugin_aawfcore.protocols.message import Message, MessageSegment


def test_neutral_message_pack_and_plaintext():
    content = Message(MessageSegment.text("hello"))
    content += MessageSegment.image(b"webp")
    content += MessageSegment.at("openid")
    assert content.extract_plain_text() == "hello"
    assert [s.type for s in content["image"]] == ["image"]
    data = pack(content)
    assert data["message_type"] == "mixed"
    assert base64.b64decode(data["segments"][1]["data_base64"]) == b"webp"
    assert data["segments"][2] == {"type": "at", "user_id": "openid"}


def test_onebot_and_qq_convert_only_in_protocol_packages():
    import nonebot

    assert (nonebot.get_plugin("nonebot_plugin_aawfqq") or nonebot.load_plugin("nonebot_plugin_aawfqq")) is not None
    assert (nonebot.get_plugin("nonebot_plugin_aawfonebot") or nonebot.load_plugin("nonebot_plugin_aawfonebot")) is not None
    from nonebot_plugin_aawfqq.router import pages
    from nonebot_plugin_aawfonebot.router import outbound

    payload = pack(Message([
        MessageSegment.text("ok"),
        MessageSegment.image(b"image"),
        MessageSegment.reply(122),
    ]))["segments"]
    assert [s.type for s in pages(payload)[0]] == ["text", "file_image", "reference"]
    assert [s.type for s in outbound(payload)] == ["text", "image", "reply"]
