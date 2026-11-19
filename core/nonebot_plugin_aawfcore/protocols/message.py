"""适配器无关的最小消息模型。

业务层只产生文本、图片、提醒对象；QQ/OneBot 在发送前转换为其原生 Message。
不在这里 import 任何平台专用适配器。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MessageSegment:
    type: str
    data: dict[str, Any]

    @staticmethod
    def text(content: str) -> "MessageSegment":
        return MessageSegment("text", {"text": str(content)})

    @staticmethod
    def image(content: bytes | str) -> "MessageSegment":
        return MessageSegment("image", {"file": content})

    @staticmethod
    def at(user_id: str) -> "MessageSegment":
        return MessageSegment("at", {"qq": str(user_id)})

    @staticmethod
    def reply(message_id: str | int) -> "MessageSegment":
        return MessageSegment("reply", {"id": str(message_id)})

    def __str__(self) -> str:
        if self.type == "text":
            return self.data["text"]
        if self.type == "at":
            return f"[CQ:at,qq={self.data['qq']}]"
        if self.type == "reply":
            return f"[CQ:reply,id={self.data['id']}]"
        return "[image]"


class Message(list[MessageSegment]):
    def __init__(self, items=None):
        super().__init__()
        if items is not None:
            self += items

    def __iadd__(self, other):
        if isinstance(other, str):
            self.append(MessageSegment.text(other))
        elif isinstance(other, MessageSegment):
            self.append(other)
        else:
            self.extend(other)
        return self

    def __add__(self, other):
        result = Message(self)
        result += other
        return result

    def __getitem__(self, index):
        if isinstance(index, str):
            return Message(segment for segment in self if segment.type == index)
        return super().__getitem__(index)

    def extract_plain_text(self) -> str:
        return "".join(str(segment.data["text"]) for segment in self if segment.type == "text")

    def __str__(self) -> str:
        return "".join(str(segment) for segment in self)
