"""Unified single-distribution protocol conversion regression."""
from nonebot_plugin_aawarframe.protocols.message import Message, MessageSegment
from nonebot_plugin_aawarframe.router import convert

def test_neutral_message_and_plaintext():
    content = Message([MessageSegment.text("hello"), MessageSegment.image(b"webp")])
    assert content.extract_plain_text() == "hello"
    assert [segment.type for segment in content["image"]] == ["image"]

def test_onebot_and_qq_conversion():
    message = Message([MessageSegment.text("ok"), MessageSegment.image(b"image"), MessageSegment.reply(122)])
    qq = convert(message, "qq")
    ob = convert(message, "onebot")
    assert [segment.type for segment in qq[0]] == ["text", "file_image", "reference"]
    assert [segment.type for segment in ob[0]] == ["text", "image", "reply"]

def test_multiple_images_become_multiple_qq_messages():
    result = convert(Message([MessageSegment.image(b"a"), MessageSegment.image(b"b")]), "qq")
    assert len(result) == 2
