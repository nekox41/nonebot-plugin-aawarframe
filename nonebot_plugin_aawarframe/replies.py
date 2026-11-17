"""可编辑的回复目录：文本模板、消息段及卡片文案集中从 TOML 读取。

静态模板与业务数据分离；TOML 不执行 Python，不解析输入中的 CQ 码。
图片、@、引用、戳一戳均以独立 OneBot 消息段/动作实现。
"""

import asyncio
import logging
import re
import shutil
import threading
import tomllib
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment

logger = logging.getLogger(__name__)
BUNDLED = Path(__file__).with_name("replies.toml")
VARIABLE = re.compile(r"%([A-Z][A-Z0-9_]*)%")
MAX_SIZE = 1024 * 1024
SEGMENT_TYPES = {"face", "record", "video", "file", "music", "share", "location"}


@dataclass
class ReplyPlan:
    message: Message = field(default_factory=Message)
    pokes: list[str] = field(default_factory=list)
    reactions: list[tuple[int, str]] = field(default_factory=list)


class ReplyCatalog:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.defaults = self._read(BUNDLED)
        self.values = self.defaults
        self.path: Path | None = None
        self.signature: tuple[int, int] | None = None
        self.phrases: dict[str, str] = {}
        self.invalid_signature: tuple[int, int] | None = None

    @staticmethod
    def _read(path: Path) -> dict:
        if path.stat().st_size > MAX_SIZE:
            raise ValueError("回复文件超过 1 MiB，请精简内容")
        with path.open("rb") as file:
            data = tomllib.load(file)
        for section in ("text", "messages", "phrases"):
            if not isinstance(data.get(section), dict):
                raise ValueError(f"回复配置缺少 [{section}] 表")
        if not all(isinstance(value, str) for value in data["text"].values()):
            raise ValueError("[text] 的值必须为字符串")
        if not all(isinstance(value, str) for value in data["phrases"].values()):
            raise ValueError("[phrases] 的值必须为字符串")
        for key, segments in data["messages"].items():
            if not isinstance(segments, list) or not all(
                isinstance(segment, dict) for segment in segments
            ):
                raise ValueError(f"消息 {key} 必须是消息段数组")
            for segment in segments:
                if segment.get("type") not in {
                    "text", "content", "at", "reply", "image", "poke", "reaction", "segment"
                }:
                    raise ValueError(f"消息 {key} 含有未知段类型")
        return data

    def configure(self, path: Path) -> None:
        """将完整默认配置复制到数据目录，仅首启创建；之后不覆盖用户编辑。"""
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                shutil.copyfile(BUNDLED, path)
            self.path = path
            self.signature = None
            self._reload()

    def _reload(self) -> None:
        if self.path is None:
            return
        try:
            stat = self.path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature in {self.signature, self.invalid_signature}:
                return
            user = self._read(self.path)
            # 新增键从包内默认配置补齐，已有用户自定义配置不被升级覆盖。
            merged = {
                section: {**self.defaults[section], **user[section]}
                for section in ("text", "messages", "phrases")
            }
            altered = {
                default: merged["phrases"][key]
                for key, default in self.defaults["phrases"].items()
                if key in merged["phrases"] and merged["phrases"][key] != default
            }
            self.values = merged
            self.phrases = altered
            self.signature = signature
            self.invalid_signature = None
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            # 人手编辑一半时不会导致机器人发送消息失败。
            try:
                stat = self.path.stat() if self.path is not None else None
                if stat is not None:
                    self.invalid_signature = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                pass
            logger.exception("回复文件加载失败，沿用上一次有效配置：%s", self.path)

    def reset(self) -> None:
        """关闭运行时后恢复包内默认设置，避免持有临时测试目录路径。"""
        with self.lock:
            self.path = None
            self.signature = None
            self.invalid_signature = None
            self.values = self.defaults
            self.phrases = {}

    def _section(self, name: str) -> dict:
        with self.lock:
            self._reload()
            return self.values[name]

    def text(self, key: str, **variables: Any) -> str:
        template = self._section("text")[key]
        try:
            rendered = self.format(template, variables)
        except ValueError:
            # 配置里误写了 %UNDEFINED% 时，不让上游业务命令失败。
            default = self.defaults["text"][key]
            if template == default:
                raise
            logger.warning("回复文本 %s 包含无效变量，临时使用默认文案", key)
            rendered = self.format(default, variables)
        return self.localize(rendered)

    @staticmethod
    def format(template: str, variables: dict[str, Any]) -> str:
        """只替换 %KEY%，不支持表达式求值/递归替换/用户输入执行。"""
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                raise ValueError(f"回复模板缺少变量 {name}")
            value = variables[name]
            return "" if value is None else str(value)
        return VARIABLE.sub(replace, template)

    def localize(self, text: str, *, html: bool = False) -> str:
        with self.lock:
            self._reload()
            replacements = dict(self.phrases)
        if not replacements:
            return text
        originals = sorted(replacements, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(item) for item in originals))
        return pattern.sub(
            lambda m: escape(replacements[m.group(0)], quote=True)
            if html else replacements[m.group(0)],
            text,
        )

    def plan(self, key: str, **variables: Any) -> ReplyPlan:
        definition = self._section("messages").get(key)
        if definition is None:
            raise KeyError(f"未定义回复消息 {key}")
        try:
            return self._build_plan(key, definition, variables)
        except (ValueError, KeyError, TypeError, AttributeError):
            default = self.defaults["messages"].get(key)
            if default is None or definition == default:
                raise
            logger.exception("回复消息 %s 的自定义消息段无效，回退默认消息段", key)
            return self._build_plan(key, default, variables)

    def _build_plan(
        self, key: str, definition: list[dict], variables: dict[str, Any]
    ) -> ReplyPlan:
        result = ReplyPlan()
        for segment in definition:
            kind = segment["type"]
            condition = segment.get("when")
            if condition and not variables.get(condition):
                continue
            if kind == "text":
                if "key" in segment:
                    value = self.text(segment["key"], **variables)
                else:
                    value = self.localize(self.format(segment.get("value", ""), variables))
                if value:
                    result.message += MessageSegment.text(value)
            elif kind == "content":
                value = variables.get(segment.get("name", "CONTENT"))
                if isinstance(value, Message):
                    result.message += value
                elif isinstance(value, MessageSegment):
                    result.message += value
                elif isinstance(value, list):
                    result.message.extend(value)
                elif value is not None:
                    result.message += MessageSegment.text(self.localize(str(value)))
            elif kind in {"at", "reply", "poke"}:
                key_name = "target" if kind != "reply" else "message_id"
                ident = self.format(str(segment.get(key_name, "")), variables)
                if not ident or not ident.isdecimal():
                    if segment.get("optional", False):
                        continue
                    raise ValueError(f"回复消息 {key} 的 {kind} 目标必须为数字")
                if kind == "at":
                    result.message += MessageSegment.at(ident)
                elif kind == "reply":
                    result.message += MessageSegment.reply(int(ident))
                else:
                    result.pokes.append(ident)
            elif kind == "reaction":
                # QQ 表情回应是对原消息执行 set_msg_emoji_like，不是回复消息段。
                message_id = self.format(str(segment.get("message_id", "")), variables)
                emoji_id = self.format(str(segment.get("emoji_id", "")), variables)
                if not message_id.isdecimal() or not emoji_id.isdecimal():
                    if segment.get("optional", False):
                        continue
                    raise ValueError(f"回复消息 {key} 的 reaction 参数必须是数字")
                result.reactions.append((int(message_id), emoji_id))
            elif kind == "image":
                # 用 name 读取运行时图片（例如查询卡片），也可用 file 设置
                # 静态图片的 OneBot file / URL；两者不依赖手工 CQ:image 文本。
                image = (
                    self.format(str(segment["file"]), variables)
                    if "file" in segment
                    else variables.get(segment.get("name", "IMAGE"))
                )
                if image is None:
                    if segment.get("optional", False):
                        continue
                    raise ValueError(f"回复消息 {key} 缺少图片")
                images = image if isinstance(image, list) else [image]
                for item in images:
                    result.message += MessageSegment.image(item)
            else:
                # 其他 OneBot 消息段：仅显式允许的 segment_type，不将 CQ 文本当代码。
                segment_type = segment.get("segment_type")
                if segment_type not in SEGMENT_TYPES:
                    raise ValueError(f"不支持消息段类型 {segment_type!r}")
                data = {
                    name: self.format(str(value), variables)
                    for name, value in segment.get("data", {}).items()
                }
                result.message += MessageSegment(segment_type, data)
        return result

    async def send_reactions(self, bot: Any, plan: ReplyPlan) -> None:
        """NapCat 表情回应，不支持时不影响原回复。"""
        for message_id, emoji_id in plan.reactions:
            try:
                await asyncio.wait_for(
                    bot.call_api(
                        "set_msg_emoji_like",
                        message_id=message_id,
                        emoji_id=emoji_id,
                    ),
                    timeout=5,
                )
            except Exception:
                logger.warning("当前 OneBot 后端不支持消息表情回应", exc_info=True)

    async def send_actions(
        self, bot: Any, plan: ReplyPlan, *, group_id=None
    ) -> None:
        await self.send_reactions(bot, plan)
        await self.send_pokes(bot, plan, group_id=group_id)

    async def send_pokes(self, bot: Any, plan: ReplyPlan, *, group_id=None) -> None:
        """戳一戳使用 NapCat/Go-CQ 的扩展 API；不能伪装成普通文本消息段。"""
        for user_id in plan.pokes:
            try:
                if group_id is not None:
                    await asyncio.wait_for(
                        bot.call_api(
                            "group_poke", group_id=int(group_id), user_id=int(user_id)
                        ),
                        timeout=5,
                    )
                else:
                    await asyncio.wait_for(
                        bot.call_api("friend_poke", user_id=int(user_id)),
                        timeout=5,
                    )
            except Exception:
                # 不兼容戳一戳 API 的 OneBot 实现不会影响原本的回复。
                logger.warning("当前 OneBot 后端不支持戳一戳操作", exc_info=True)


replies = ReplyCatalog()
