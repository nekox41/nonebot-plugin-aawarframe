"""命令响应类型不与某个平台的 MessageSegment 耦合。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from nonebot_plugin_aawarframe.api import pack
from nonebot_plugin_aawarframe.commands import router


async def test_command_image_is_returned_as_protocol_neutral_response():
    runtime = SimpleNamespace(renderer=SimpleNamespace(
        render=AsyncMock(return_value=[b"webp-fixture"])
    ))
    from nonebot_plugin_aawarframe.models.common import Card

    result = await router.response(Card(title="裂缝", source="test"), runtime)
    assert [s.type for s in result] == ["image"]
    packed = pack(result)
    assert packed["message_type"] == "image"
    assert packed["segments"][0]["type"] == "image"
    assert "reply" not in [s["type"] for s in packed["segments"]]
