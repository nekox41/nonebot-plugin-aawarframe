# 作用：验证命令直接发送结果，不附加消息引用。
# 编写日期：2026-11-07
# 作者：Aameow

from types import SimpleNamespace
from unittest.mock import AsyncMock

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from nonebot_plugin_aawarframe.commands import router


async def test_command_sends_result_without_reply_segment(monkeypatch):
    handlers = []
    command = SimpleNamespace(handle=lambda: lambda function: handlers.append(function))
    monkeypatch.setattr(router, "on_message", lambda *args, **kwargs: command)
    result = Message(MessageSegment.image(b"webp-fixture"))
    monkeypatch.setattr(router, "dispatch", AsyncMock(return_value=result))
    router.register("裂缝", set(), "fissures")
    matcher = SimpleNamespace(finish=AsyncMock())
    await handlers[0](matcher, {"aawarframe_arguments": ""})
    sent = matcher.finish.await_args.args[0]
    assert sent == result
    assert [segment.type for segment in sent] == ["image"]
