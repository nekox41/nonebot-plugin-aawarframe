"""群订阅持久化、夜灵周期、去重、取消及主动通知测试。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.models.common import Snapshot
from nonebot_plugin_aawarframe.models.worldstate import CycleState
from nonebot_plugin_aawarframe.subscriptions.rules import (
    next_cetus_occurrence,
    parse_cetus_rule,
)
from nonebot_plugin_aawarframe.subscriptions.service import SubscriptionService
from nonebot_plugin_aawarframe.subscriptions.store import SubscriptionStore

UTC = timezone.utc


def test_rule_and_next_night():
    assert parse_cetus_rule("地球平原") == 15
    assert parse_cetus_rule("夜灵平野 提前5分钟") == 5
    with pytest.raises(ValueError):
        parse_cetus_rule("地球平原 提前91分钟")
    now = datetime(2026, 11, 17, 0, 0, tzinfo=UTC)
    cycle = CycleState(
        location="夜灵平野",
        state="白天",
        next_state="黑夜",
        expiry=now + timedelta(minutes=20),
        basis="test",
    )
    first = next_cetus_occurrence(cycle, now, now, 15)
    assert first.due_at == now + timedelta(minutes=5)
    assert first.event_at == now + timedelta(minutes=20)
    # 订阅发生在本轮提醒触发之后，须跳到下轮，而不是立即补发。
    late = next_cetus_occurrence(
        cycle, now + timedelta(minutes=6), now + timedelta(minutes=6), 15
    )
    assert late.due_at == first.due_at + timedelta(minutes=150)
    night = CycleState(
        location="夜灵平野",
        state="黑夜",
        next_state="白天",
        expiry=now + timedelta(minutes=50),
        basis="test",
    )
    assert next_cetus_occurrence(night, now, now, 15).event_at == (
        now + timedelta(minutes=150)
    )


def test_subscriptions_persist_and_are_scoped(tmp_path):
    path = tmp_path / "sub.sqlite3"
    store = SubscriptionStore(path)
    first, created = store.subscribe("bot", "group-a", "user", 15)
    assert created
    again, created = store.subscribe("bot", "group-a", "user", 15)
    assert not created and again.id == first.id
    other, created = store.subscribe("bot", "group-b", "user", 15)
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
    provider = SimpleNamespace(fetch=AsyncMock(return_value=Snapshot(data={"test": True}, source="test")))
    fake_bot = SimpleNamespace(send_group_msg=AsyncMock(return_value={"message_id": 123}))
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.cetus_cycle",
        lambda data, stamp: (cycle, []),
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {"bot": fake_bot},
    )
    service = SubscriptionService(tmp_path, provider)
    sub, _ = service.store.subscribe("bot", "10001", "20002", 15)
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
    created = await service.handle("subscribe", "地球平原", ("bot", "100", "200"))
    assert "订阅成功" in created
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
