"""新增订阅类型、初次基线、图片推送、去重与仲裁提前提醒。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.models.common import Snapshot
from nonebot_plugin_aawarframe.subscriptions.rules import parse_rule
from nonebot_plugin_aawarframe.subscriptions.service import SubscriptionService
from nonebot_plugin_aawarframe.subscriptions.sources import (
    arbitration_events, bounty_events, fissure_events, market_events,
)
from nonebot_plugin_aawarframe.subscriptions.store import SubscriptionStore

UTC = timezone.utc


def _stamp(value):
    return {"$date": {"$numberLong": str(int(value.timestamp() * 1000))}}


def _fissure(node, now):
    return {
        "Node": node, "Modifier": "VoidT1",
        "Activation": _stamp(now - timedelta(seconds=10)),
        "Expiry": _stamp(now + timedelta(minutes=50)),
    }


def _bounty(now):
    return {
        "Tag": "CetusSyndicate",
        "Activation": _stamp(now - timedelta(seconds=10)),
        "Expiry": _stamp(now + timedelta(minutes=50)),
        "Jobs": [{"jobType": "/Lotus/Jobs/Quest", "rewards": "RewardPool",
                  "minEnemyLevel": 5, "maxEnemyLevel": 15}],
    }


def _order(order_id, price=40):
    return SimpleNamespace(
        id=order_id, type="sell", visible=True, platinum=price, per_trade=1,
        rank=None, subtype=None, quantity=4,
        user=SimpleNamespace(
            name="Seller", status="online", platform="pc", crossplay=True
        ),
    )


def test_rules_are_normalized_and_bounded():
    assert parse_rule("夜灵").kind == "cetus_night"
    assert parse_rule("地球平原").rule == {"lead_minutes": 15}
    fissure = parse_rule("裂缝 钢铁 后纪 生存")
    assert fissure.rule == {
        "tier": "后纪", "planet": "", "mission": "生存", "hard": True
    }
    assert parse_rule("裂缝 虚空 生存").rule["planet"] == "虚空"
    assert parse_rule("仲裁 生存").rule["mission"] == "生存"
    assert parse_rule("赏金 金星 钢铁之路").rule["region"] == "金星"
    assert parse_rule("wm 伯斯顿 卖价<=50").rule["price"] == 50
    for invalid in ("夜灵 提前5分钟", "仲裁 防御 提前10分钟",
                    "wm", "赏金 月球", "裂缝 古纪 后纪"):
        with pytest.raises(ValueError):
            parse_rule(invalid)


def test_world_event_extractors(monkeypatch):
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.sources.node_info",
        lambda node: {"name": "测试节点", "missionName": "生存", "systemName": "虚空"},
    )
    fissures, status = fissure_events(
        {"ActiveMissions": [_fissure("SolNode1", now)]}, now,
        parse_rule("裂缝 古纪 生存").rule,
    )
    assert len(fissures) == 1 and "1 项" in status
    assert fissures[0].key == fissure_events(
        {"ActiveMissions": [_fissure("SolNode1", now)]}, now,
        parse_rule("裂缝 古纪 生存").rule,
    )[0][0].key
    assert fissure_events(
        {"ActiveMissions": [_fissure("SolNode1", now)]}, now,
        parse_rule("裂缝 钢铁 古纪").rule,
    )[0] == []
    bounties, _ = bounty_events(
        {"SyndicateMissions": [_bounty(now)]}, now,
        parse_rule("赏金 地球 常规").rule,
    )
    assert len(bounties) == 1 and bounties[0].title == "地球赏金更新"


def test_arbitration_uses_fixed_15_minute_warning():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    start = now + timedelta(minutes=15)
    events, status = arbitration_events(
        [(int(start.timestamp()), "node")],
        {"node": {"missionName": "生存", "name": "测试节点", "systemName": "火星"}},
        now, now - timedelta(minutes=2), parse_rule("仲裁 生存").rule,
    )
    assert len(events) == 1
    assert events[0].due_at == now
    assert events[0].event_at == start
    assert "下场" in status


def test_market_filters_by_real_price_and_online_status():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    rule = {"name": "伯斯顿", "slug": "burston", "price": 50,
            "rank": None, "subtype": None}
    events, status = market_events(
        SimpleNamespace(sell=[_order("ok", 40), _order("expensive", 60)], buy=[]),
        now, rule,
    )
    assert len(events) == 1 and events[0].key == "market-order:ok"
    assert "最低 40" in status


@pytest.mark.asyncio
async def test_fissure_initial_baseline_new_event_image_and_restart(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=10)
    data = {"ActiveMissions": [_fissure("old", now)]}
    provider = SimpleNamespace(
        fetch=AsyncMock(return_value=Snapshot(data=data, source="test"))
    )
    renderer = SimpleNamespace(render=AsyncMock(return_value=[b"image-content"]))
    bot = SimpleNamespace(send_group_msg=AsyncMock(return_value={"message_id": 100}))
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.sources.node_info",
        lambda node: {"name": node, "missionName": "生存", "systemName": "虚空"},
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {"bot": bot},
    )
    service = SubscriptionService(tmp_path, provider, renderer=renderer)
    rule = parse_rule("裂缝 古纪 生存")
    service.store.subscribe("bot", "100", "200", rule.kind, rule.rule)
    service.store.subscribe("bot", "100", "200", "market", {
        "slug": "test", "name": "其他物品", "price": 50
    })
    await service._tick(now)
    bot.send_group_msg.assert_not_awaited()  # 初次基线不通知旧裂缝

    next_now = now + timedelta(seconds=20)
    data["ActiveMissions"].append(_fissure("new", next_now))
    await service._tick(next_now)
    assert bot.send_group_msg.await_count == 1
    message = bot.send_group_msg.await_args.kwargs["message"]
    assert "[CQ:at,qq=200]" in str(message)
    assert any(segment.type == "image" for segment in message)
    card = renderer.render.await_args.args[0]
    assert card.sections[0].title == "本次触发"
    assert any("Market" in row[0] for row in card.sections[1].rows)
    await service.close()

    # 重启以后仍保留事件基线和发件箱去重。
    restarted = SubscriptionService(tmp_path, provider, renderer=renderer)
    await restarted._tick(next_now)
    assert bot.send_group_msg.await_count == 1
    await restarted.close()


@pytest.mark.asyncio
async def test_arbitration_send_without_worldstate(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=10)
    at = now + timedelta(minutes=15)
    arbit = SimpleNamespace(
        schedule=[(int(at.timestamp()), "node")],
        nodes={"node": {"name": "测试", "missionName": "生存", "systemName": "火星"}},
    )
    bot = SimpleNamespace(send_group_msg=AsyncMock())
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {"bot": bot},
    )
    provider = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("no worldstate")))
    service = SubscriptionService(tmp_path, provider, arbitration=arbit)
    service.store.subscribe("bot", "100", "200", "arbitration", {"mission": "生存"})
    await service._tick(now)
    provider.fetch.assert_not_awaited()
    assert bot.send_group_msg.await_count == 1
    await service._tick(now)
    assert bot.send_group_msg.await_count == 1
    await service.close()


@pytest.mark.asyncio
async def test_market_baseline_and_new_order_only(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=10)
    orders = SimpleNamespace(sell=[_order("old")], buy=[])
    provider = SimpleNamespace(
        orders=AsyncMock(return_value=Snapshot(data=orders, source="market"))
    )
    market = SimpleNamespace(provider=provider)
    bot = SimpleNamespace(send_group_msg=AsyncMock())
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {"bot": bot},
    )
    world = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("not needed")))
    service = SubscriptionService(tmp_path, world, market=market)
    service.store.subscribe("bot", "100", "200", "market", {
        "slug": "burston", "name": "伯斯顿", "price": 50,
        "rank": None, "subtype": None,
    })
    await service._tick(now)
    assert bot.send_group_msg.await_count == 0
    assert provider.orders.await_count == 1
    await service._tick(now + timedelta(seconds=30))
    assert provider.orders.await_count == 1
    orders.sell.append(_order("new", 35))
    await service._tick(now + timedelta(minutes=3))
    assert provider.orders.await_count == 2
    assert bot.send_group_msg.await_count == 1
    await service.close()


def test_store_baselines_persist_and_scope(tmp_path):
    path = tmp_path / "sub.sqlite3"
    store = SubscriptionStore(path)
    sub, created = store.subscribe(
        "bot", "group-a", "user", "fissure", parse_rule("裂缝 古纪 生存").rule
    )
    assert created
    assert not store.subscribe(
        "bot", "group-a", "user", "fissure", parse_rule("裂缝 古纪 生存").rule
    )[1]
    assert store.subscribe(
        "bot", "group-b", "user", "fissure", parse_rule("裂缝 古纪 生存").rule
    )[1]
    now = datetime.now(UTC)
    from nonebot_plugin_aawarframe.subscriptions.sources import Event
    event = Event("event-1", "裂缝", "说明", now, now)
    assert store.observe(sub.id, [event], now) == 0
    assert store.observe(sub.id, [event], now) == 0
    assert store.observe(sub.id, [Event("event-2", "新裂缝", "说明", now, now)], now) == 1
    store.close()
    reopened = SubscriptionStore(path)
    assert reopened.observe(sub.id, [event], now) == 0
    assert reopened.observe(
        sub.id, [Event("event-2", "新裂缝", "说明", now, now)], now
    ) == 0
    reopened.close()


def test_source_failure_does_not_cancel_first_event_baseline(tmp_path):
    now = datetime.now(UTC)
    store = SubscriptionStore(tmp_path / "state.sqlite3")
    rule = parse_rule("裂缝 古纪 生存")
    sub, _ = store.subscribe("bot", "group", "user", rule.kind, rule.rule)
    store.set_status(sub.id, "世界状态暂不可用")
    from nonebot_plugin_aawarframe.subscriptions.sources import Event
    event = Event("existing", "任务", "信息", now, now)
    assert store.observe(sub.id, [event], now) == 0
    assert store.observe(
        sub.id, [Event("new", "任务", "信息", now, now)], now
    ) == 1
    store.close()


def test_challenge_region_rotation_without_jobs():
    now = datetime.now(UTC)
    raw = {"SyndicateMissions": [{
        "Tag": "EntratiLabSyndicate",
        "Activation": _stamp(now - timedelta(minutes=1)),
        "Expiry": _stamp(now + timedelta(minutes=50)),
        "Nodes": [],
    }]}
    events, status = bounty_events(raw, now, parse_rule("赏金 圣所").rule)
    assert len(events) == 1
    assert "新一轮任务" in events[0].detail
    assert "圣所" in status


@pytest.mark.asyncio
async def test_market_late_keys_get_checked_in_later_window(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=10)
    data = Snapshot(data=SimpleNamespace(sell=[], buy=[]), source="market")
    provider = SimpleNamespace(orders=AsyncMock(return_value=data))
    market = SimpleNamespace(provider=provider)
    bot = SimpleNamespace(send_group_msg=AsyncMock())
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {"bot": bot},
    )
    service = SubscriptionService(
        tmp_path,
        SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("not needed"))),
        market=market,
    )
    for index in range(9):
        service.store.subscribe(
            "bot", "100", str(index), "market",
            {"slug": f"item{index}", "name": f"物品{index}", "price": 50},
        )
    await service._tick(now)
    assert provider.orders.await_count == 8
    await service._tick(now + timedelta(minutes=3))
    queried = {call.args[0] for call in provider.orders.await_args_list}
    assert queried == {f"item{i}" for i in range(9)}
    await service.close()
