"""群订阅持久化、夜灵周期、去重、取消及主动通知测试。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawfcore.models.common import Snapshot
from nonebot_plugin_aawfcore.models.worldstate import CycleState
from nonebot_plugin_aawfcore.subscriptions.rules import (
    next_cetus_occurrence,
    parse_cetus_rule,
)
from nonebot_plugin_aawfcore.subscriptions.service import SubscriptionService
from nonebot_plugin_aawfcore.subscriptions.store import SubscriptionStore

UTC = timezone.utc


def test_rule_and_next_night():
    assert parse_cetus_rule("地球平原") is None
    assert parse_cetus_rule("夜灵") is None
    for invalid in (
        "地球平原 提前5分钟",
        "夜灵 提前15分钟",
        "夜灵平野",
        "希图斯",
        "地球平原 其他",
    ):
        with pytest.raises(ValueError, match="固定提前 15 分钟"):
            parse_cetus_rule(invalid)
    now = datetime(2026, 11, 17, 0, 0, tzinfo=UTC)
    cycle = CycleState(
        location="夜灵平野",
        state="白天",
        next_state="黑夜",
        expiry=now + timedelta(minutes=20),
        basis="test",
    )
    first = next_cetus_occurrence(cycle, now, now)
    assert first.due_at == now + timedelta(minutes=5)
    assert first.event_at == now + timedelta(minutes=20)
    # 订阅发生在本轮提醒触发之后，须跳到下轮，而不是立即补发。
    late = next_cetus_occurrence(
        cycle, now + timedelta(minutes=6), now + timedelta(minutes=6)
    )
    assert late.due_at == first.due_at + timedelta(minutes=150)
    night = CycleState(
        location="夜灵平野",
        state="黑夜",
        next_state="白天",
        expiry=now + timedelta(minutes=50),
        basis="test",
    )
    assert next_cetus_occurrence(night, now, now).event_at == (
        now + timedelta(minutes=150)
    )


def test_subscriptions_persist_and_are_scoped(tmp_path):
    path = tmp_path / "sub.sqlite3"
    store = SubscriptionStore(path)
    first, created = store.subscribe("bot", "group-a", "user")
    assert created
    again, created = store.subscribe("bot", "group-a", "user")
    assert not created and again.id == first.id
    other, created = store.subscribe("bot", "group-b", "user")
    assert created and other.id != first.id
    assert not store.remove(first.id, "bot", "group-b", "user")
    store.close()
    reopened = SubscriptionStore(path)
    assert [s.id for s in reopened.list_for("bot", "group-a", "user")] == [first.id]
    assert reopened.remove(first.id, "bot", "group-a", "user")
    assert not reopened.list_for("bot", "group-a", "user")
    reopened.close()


@pytest.mark.asyncio
async def test_scheduler_sends_once_and_restarts(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=30)
    cycle = CycleState(
        location="夜灵平野",
        state="白天",
        next_state="黑夜",
        expiry=now + timedelta(minutes=15),
        basis="test",
    )
    provider = SimpleNamespace(
        fetch=AsyncMock(return_value=Snapshot(data={"test": True}, source="test"))
    )
    fake_bot = SimpleNamespace(send_group_msg=AsyncMock(return_value={"message_id": 123}))
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.service.cetus_cycle",
        lambda data, stamp: (cycle, []),
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.service.get_bots",
        lambda: {"bot": fake_bot},
    )
    service = SubscriptionService(tmp_path, provider)
    sub, _ = service.store.subscribe("bot", "10001", "20002")
    await service._tick(now)
    await service._tick(now)
    assert fake_bot.send_group_msg.await_count == 1
    sent = fake_bot.send_group_msg.await_args.kwargs
    assert sent["group_id"] == 10001
    assert "[CQ:at,qq=20002]" in str(sent["message"])
    assert sub.id > 0
    await service.close()

    # 已发送事件的唯一键能在进程重启后继续防重。
    restarted = SubscriptionService(tmp_path, provider)
    await restarted._tick(now)
    assert fake_bot.send_group_msg.await_count == 1
    await restarted.close()


@pytest.mark.asyncio
async def test_commands_and_cancel(tmp_path):
    provider = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("offline")))
    service = SubscriptionService(tmp_path, provider)
    created = await service.handle("subscribe", "夜灵", ("bot", "100", "200"))
    assert "订阅成功" in created
    already = await service.handle("subscribe", "地球平原", ("bot", "100", "200"))
    assert "该订阅已存在" in already
    assert len(service.store.list_for("bot", "100", "200")) == 1
    with pytest.raises(Exception, match="用法：订阅 夜灵"):
        await service.handle("subscribe", "夜灵 提前5分钟", ("bot", "100", "200"))
    assert "暂时无法" in created
    assert "黑夜前 15 分钟" in await service.handle(
        "list_subscriptions", "", ("bot", "100", "200")
    )
    sub = service.store.list_for("bot", "100", "200")[0]
    assert "未找到" not in await service.handle(
        "unsubscribe", str(sub.id), ("bot", "100", "200")
    )
    assert "暂无订阅" in await service.handle(
        "list_subscriptions", "", ("bot", "100", "200")
    )
    await service.close()


@pytest.mark.asyncio
async def test_stale_snapshot_suppresses_notifications(tmp_path, monkeypatch):
    provider = SimpleNamespace(
        fetch=AsyncMock(
            return_value=Snapshot(data={"test": True}, source="test", stale=True)
        )
    )
    fake_bot = SimpleNamespace(send_group_msg=AsyncMock())
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.service.get_bots",
        lambda: {"bot": fake_bot},
    )
    service = SubscriptionService(tmp_path, provider)
    service.store.subscribe("bot", "100", "200")
    await service._tick()
    fake_bot.send_group_msg.assert_not_awaited()
    await service.close()

def test_migrate_previously_configurable_night_rules(tmp_path):
    """早期 Draft 的可配置时间应合并为同一个 15 分钟订阅。"""
    path = tmp_path / "legacy.sqlite3"
    store = SubscriptionStore(path)
    first, _ = store.subscribe("bot", "group", "user")
    with store.db:
        store.db.execute(
            "INSERT INTO subscriptions(bot_id,group_id,user_id,kind,rule_json,created_at) "
            "VALUES ('bot','group','user','cetus_night',?,?)",
            ('{"lead_minutes":5}', datetime.now(UTC).timestamp()),
        )
    store.close()
    migrated = SubscriptionStore(path)
    rows = migrated.list_for("bot", "group", "user")
    assert len(rows) == 1 and rows[0].id == first.id
    assert migrated.db.execute(
        "SELECT rule_json FROM subscriptions WHERE id=?", (first.id,)
    ).fetchone()[0] == '{"lead_minutes":15}'
    migrated.close()
