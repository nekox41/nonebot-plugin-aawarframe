"""可编辑回复目录：变量、消息段、戳一戳、卡片短句和损坏配置回退。"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from nonebot_plugin_aawarframe.replies import ReplyCatalog


def edit(path: Path, original: str, replacement: str) -> None:
    raw = path.read_text(encoding="utf-8")
    assert original in raw, original
    path.write_text(raw.replace(original, replacement, 1), encoding="utf-8")
    # 测试环境有时毫秒级文件时间戳相同，确保触发热更新。
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


def test_default_catalog_and_file_copy(tmp_path):
    catalog = ReplyCatalog()
    path = tmp_path / "aawarframe" / "replies.toml"
    catalog.configure(path)
    assert path.is_file()
    assert catalog.text(
        "SUB_CREATED", CODE=4, TYPE="紫卡市场 · 伯斯顿 · 低于1000白金"
    ) == "订阅成功（编号 4）：紫卡市场 · 伯斯顿 · 低于1000白金。"
    assert catalog.text("SUB_BASELINE").startswith("\n首次检查")
    assert len(catalog.defaults["phrases"]) >= 300
    before = path.read_bytes()
    catalog.configure(path)
    assert before == path.read_bytes()
    catalog.reset()
    assert catalog.path is None


def test_hot_reload_reordering_and_multiline(tmp_path):
    catalog = ReplyCatalog()
    path = tmp_path / "replies.toml"
    catalog.configure(path)
    edit(
        path,
        'SUB_CREATED = "订阅成功（编号 %CODE%）：%TYPE%。"',
        'SUB_CREATED = "武器：%WEAPON%\\n价格：%LIMIT%\\n编号：%CODE%\\n%TYPE%"',
    )
    result = catalog.text(
        "SUB_CREATED",
        CODE=4,
        TYPE="紫卡市场",
        WEAPON="伯斯顿",
        LIMIT=1000,
    )
    assert result == "武器：伯斯顿\n价格：1000\n编号：4\n紫卡市场"
    edit(
        path,
        'SUB_CREATED = "武器：%WEAPON%\\n价格：%LIMIT%\\n编号：%CODE%\\n%TYPE%"',
        'SUB_CREATED = "订阅 #%CODE%：%TYPE%"',
    )
    assert catalog.text("SUB_CREATED", CODE=9, TYPE="阿耶") == "订阅 #9：阿耶"


def test_onebot_images_mentions_quotes_and_text_not_cq(tmp_path):
    catalog = ReplyCatalog()
    catalog.configure(tmp_path / "replies.toml")
    literal = "[CQ:at,qq=987654] <script>alert(1)</script>"
    msg = catalog.plan("TEXT", CONTENT=literal).message
    assert [item.type for item in msg] == ["text"]
    assert literal in msg.extract_plain_text()

    image = catalog.plan("QUERY_IMAGE", IMAGES=[b"PNG-1", b"PNG-2"]).message
    assert [item.type for item in image] == ["image", "image"]

    path = catalog.path
    assert path is not None
    edit(
        path,
        'COMMAND_ENVELOPE = [{ type = "content", name = "CONTENT" }]',
        'COMMAND_ENVELOPE = ['
        '{ type = "reply", message_id = "%MESSAGE_ID%" }, '
        '{ type = "at", target = "%USER_ID%" }, '
        '{ type = "content", name = "CONTENT" }, '
        '{ type = "image", file = "https://example.org/sample.png" }, '
        '{ type = "segment", segment_type = "face", data = { id = "14" } }, '
        '{ type = "reaction", message_id = "%MESSAGE_ID%", emoji_id = "128512" }, '
        '{ type = "poke", target = "%USER_ID%" }'
        ']',
    )
    content = Message(MessageSegment.text(literal))
    plan = catalog.plan(
        "COMMAND_ENVELOPE",
        CONTENT=content,
        MESSAGE_ID="1234",
        USER_ID="987654",
    )
    assert [segment.type for segment in plan.message] == [
        "reply", "at", "text", "image", "face"
    ]
    assert plan.pokes == ["987654"]
    assert plan.reactions == [(1234, "128512")]
    assert literal in plan.message.extract_plain_text()


@pytest.mark.asyncio
async def test_poke_extension_group_private_and_unsupported(tmp_path):
    catalog = ReplyCatalog()
    catalog.configure(tmp_path / "replies.toml")
    fake = SimpleNamespace(call_api=AsyncMock(return_value={"status": "ok"}))
    plan = catalog.plan("COMMAND_ENVELOPE", CONTENT="hello")
    plan.pokes.append("123456")
    await catalog.send_pokes(fake, plan, group_id=2468)
    fake.call_api.assert_awaited_with("group_poke", group_id=2468, user_id=123456)
    await catalog.send_pokes(fake, plan)
    fake.call_api.assert_awaited_with("friend_poke", user_id=123456)

    plan.reactions.append((777, "128512"))
    await catalog.send_reactions(fake, plan)
    fake.call_api.assert_awaited_with(
        "set_msg_emoji_like", message_id=777, emoji_id="128512"
    )
    await catalog.send_actions(fake, plan, group_id=2468)
    fake.call_api.assert_awaited_with("group_poke", group_id=2468, user_id=123456)

    fake.call_api.side_effect = RuntimeError("no poke or reaction action")
    await catalog.send_actions(fake, plan, group_id=2468)


def test_phrase_escaping_and_error_tolerant_reload(tmp_path):
    catalog = ReplyCatalog()
    path = tmp_path / "replies.toml"
    catalog.configure(path)
    key, source = next(iter(catalog.defaults["phrases"].items()))
    # 自动替换文字；HTML 内容必须被转义，不能变成可执行 DOM。
    edit(
        path,
        f'{key} = {json.dumps(source, ensure_ascii=False)}',
        f'{key} = "<script>不可信</script>"',
    )
    assert catalog.localize(source) == "<script>不可信</script>"
    assert catalog.localize(source, html=True) == "&lt;script&gt;不可信&lt;/script&gt;"

    valid = catalog.text("SUB_CREATED", CODE=1, TYPE="夜灵")
    path.write_text("[text\nbad", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert catalog.text("SUB_CREATED", CODE=1, TYPE="夜灵") == valid


@pytest.mark.asyncio
async def test_empty_optional_poke_trigger_and_notification_image():
    catalog = ReplyCatalog()
    empty = catalog.plan("POKE_RECEIVED", USER_ID="123")
    assert not empty.message and empty.pokes == []
    notify = catalog.plan("SUB_NOTIFICATION", USER_ID="123", IMAGE=b"png", FALLBACK="")
    assert [x.type for x in notify.message] == ["at", "image"]
    fallback = catalog.plan(
        "SUB_NOTIFICATION", USER_ID="123", IMAGE=None, FALLBACK="部分内容\n请查看"
    )
    assert [x.type for x in fallback.message] == ["at", "text"]
    assert fallback.message.extract_plain_text() == "\n部分内容\n请查看"


def test_unknown_variables_are_not_evaluated():
    catalog = ReplyCatalog()
    assert catalog.format("%NAME% = %CODE%", {"NAME": "__import__('os')", "CODE": 5}) == (
        "__import__('os') = 5"
    )
    with pytest.raises(ValueError, match="MISSING"):
        catalog.format("%MISSING%", {})


def test_invalid_user_variables_and_segment_specs_fall_back(tmp_path):
    catalog = ReplyCatalog()
    path = tmp_path / "replies.toml"
    catalog.configure(path)
    edit(
        path,
        'SUB_CREATED = "订阅成功（编号 %CODE%）：%TYPE%。"',
        'SUB_CREATED = "无效变量：%DOES_NOT_EXIST%"',
    )
    assert catalog.text("SUB_CREATED", CODE=4, TYPE="夜灵") == (
        "订阅成功（编号 4）：夜灵。"
    )
    edit(
        path,
        'COMMAND_ENVELOPE = [{ type = "content", name = "CONTENT" }]',
        'COMMAND_ENVELOPE = [{ type = "at", target = "%NOT_DEFINED%" }]',
    )
    message = catalog.plan("COMMAND_ENVELOPE", CONTENT="正常回复").message
    assert [segment.type for segment in message] == ["text"]
    assert message.extract_plain_text() == "正常回复"


def test_actual_card_html_and_text_fallback_use_editable_phrase(tmp_path, monkeypatch):
    from nonebot_plugin_aawarframe.models.common import Card, Section
    from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
    from nonebot_plugin_aawarframe.rendering.viewmodels import fallback_text

    catalog = ReplyCatalog()
    path = tmp_path / "replies.toml"
    catalog.configure(path)
    key, original = next(iter(catalog.defaults["phrases"].items()))
    updated = "自定义页面标题"
    edit(
        path,
        f"{key} = {json.dumps(original, ensure_ascii=False)}",
        f'{key} = "{updated}"',
    )
    card = Card(
        title=original,
        source="test",
        sections=[Section(title="测试", rows=[["类型", "说明"]])],
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.rendering.renderer.replies", catalog
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.rendering.viewmodels.replies", catalog
    )
    assert updated in CardRenderer().html(card)
    assert updated in fallback_text(card)
