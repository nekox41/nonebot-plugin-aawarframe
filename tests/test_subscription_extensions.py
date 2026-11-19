"""订阅 v2：三类裂缝、S仲裁、目标赏金、阿耶、Market、紫卡和图片提醒。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawfcore.models.common import Snapshot
from nonebot_plugin_aawfcore.subscriptions.rules import parse_rule
from nonebot_plugin_aawfcore.subscriptions.service import SubscriptionService
from nonebot_plugin_aawfcore.subscriptions.sources import arbitration_events, fissure_events
from nonebot_plugin_aawfcore.subscriptions.store import SubscriptionStore
from nonebot_plugin_aawfcore.subscriptions.targets import (
    aya_events,
    efficient_bounty_events,
    market_rank_events,
    riven_events,
)

UTC = timezone.utc


def _stamp(value):
    return {"$date": {"$numberLong": str(int(value.timestamp() * 1000))}}


def _fissure(node, now, *, hard=False, railjack=False):
    entry = {
        "Node": node,
        "Activation": _stamp(now - timedelta(seconds=10)),
        "Expiry": _stamp(now + timedelta(minutes=50)),
    }
    if railjack:
        entry["ActiveMissionTier"] = "VoidT1"
    else:
        entry["Modifier"] = "VoidT1"
        entry["Hard"] = hard
    return entry


def _order(order_id, item="abc", price=40, *, user="competing"):
    return {
        "id": order_id,
        "type": "sell",
        "itemId": item,
        "platinum": price,
        "quantity": 1,
        "perTrade": 1,
        "visible": True,
        "rank": 0,
        "user": {"status": "ingame", "ingameName": user},
    }


def test_rules_are_normalized_and_bounded():
    assert parse_rule("夜灵").kind == "cetus_night"
    assert parse_rule("地球平原").rule == {"lead_minutes": 15}
    assert parse_rule("裂缝 生存").rule == {
        "mode": "normal", "tier": "", "planet": "", "mission": "生存"
    }
    assert parse_rule("钢铁裂缝 塞德娜").rule["planet"] == "塞德娜"
    assert parse_rule("钢铁裂缝 塞德娜 生存 后纪").rule == {
        "mode": "steel", "tier": "后纪", "planet": "塞德娜", "mission": "生存"
    }
    assert parse_rule("九重天 古纪").rule["mode"] == "railjack"
    assert parse_rule("九重天").kind == "fissure"
    assert parse_rule("仲裁").rule == {}
    assert parse_rule("扎里曼").rule["region"] == "扎里曼"
    assert parse_rule("1999").kind == "bounty"
    assert parse_rule("阿耶").kind == "aya"
    assert parse_rule("wm aa_market_123").rule == {"user": "aa_market_123"}
    assert parse_rule("wmr 伯斯顿 伤害 200").rule["price"] == 200
    for invalid in (
        "夜灵 提前5分钟", "仲裁 防御", "订阅 仲裁", "赏金 地球",
        "wm", "wm 伯斯顿 卖价<=50", "裂缝 钢铁 古纪",
        "裂缝 古纪 后纪", "裂缝 任意", "wmr 伯斯顿 伤害 0",
    ):
        with pytest.raises(ValueError):
            parse_rule(invalid)


def test_three_fissure_modes_and_combined_filters(monkeypatch):
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.sources.node_info",
        lambda node: {
            "name": node, "missionName": "生存", "systemName": "塞德娜"
        },
    )
    data = {
        "ActiveMissions": [
            _fissure("normal", now),
            _fissure("steel", now, hard=True),
        ],
        "VoidStorms": [_fissure("railjack", now, railjack=True)],
    }
    for command, expected in (
        ("裂缝 生存", "normal"),
        ("钢铁裂缝 塞德娜 生存 古纪", "steel"),
        ("九重天 古纪 生存 塞德娜", "railjack"),
    ):
        result, _ = fissure_events(data, now, parse_rule(command).rule)
        assert len(result) == 1
        assert expected in result[0].detail
    assert fissure_events(data, now, parse_rule("九重天 防御").rule)[0] == []
    a = fissure_events(data, now, parse_rule("裂缝 生存").rule)[0][0]
    b = fissure_events(data, now, parse_rule("裂缝 生存").rule)[0][0]
    assert a.key == b.key


def test_arbitration_only_s_and_15_minutes():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    start = now + timedelta(minutes=15)
    nodes = {
        "s": {"missionName": "生存", "name": "S节点"},
        "a": {"missionName": "防御", "name": "A节点"},
    }
    schedule = [
        (int(start.timestamp()), "s"),
        (int((start + timedelta(hours=1)).timestamp()), "a"),
    ]
    events, status = arbitration_events(
        schedule, nodes, now, now - timedelta(minutes=1), {},
        stats=lambda key: {"grade": "S" if key == "s" else "A"},
    )
    assert len(events) == 1
    assert events[0].due_at == now
    assert events[0].event_at == start
    assert "S 级" in status


def test_quick_bounty_conditions(monkeypatch):
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    good = SimpleNamespace(
        index=4, mission="歼灭", name="简单目标", node="测试",
        objectives=["收集3个物品"], kind="常规",
    )
    blocked = SimpleNamespace(
        index=5, mission="歼灭", name="危险目标", node="测试",
        objectives=["禁用技能"], kind="常规",
    )
    good1999 = SimpleNamespace(
        index=7, mission="歼灭", name="杀毒任务", node="测试",
        objectives=[], kind="杀毒",
    )
    vault = SimpleNamespace(
        index=7, mission="捕获", name="捕获传承种", node="测试",
        objectives=["找到保险箱"], kind="杀毒",
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.targets.build_bounties",
        lambda snapshot, now, region: SimpleNamespace(
            bounty_items=[good, blocked] if region != "hex" else [good1999, vault],
            bounty_expiry=now + timedelta(hours=1),
        ),
    )
    snapshot = Snapshot(data={}, source="test")
    for region in ("扎里曼", "圣所"):
        events, status = efficient_bounty_events(snapshot, now, {"region": region})
        assert len(events) == 1
        assert "符合 1 项" in status
    events, _ = efficient_bounty_events(snapshot, now, {"region": "1999"})
    assert len(events) == 2
    assert any("捕获" in event.detail for event in events)


def test_aya_three_tents(monkeypatch):
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "nonebot_plugin_aawfcore.subscriptions.targets.build_bounties",
        lambda *args, **kwargs: SimpleNamespace(
            bounty_expiry=now + timedelta(minutes=30),
            bounty_locations={
                "帐篷 A": ["搜索并救援", "间谍"],
                "帐篷 B": ["捕获 Grineer 特工"],
                "帐篷 C": ["防御"],
            },
        ),
    )
    events, status = aya_events(Snapshot(data={}, source="test"), now)
    assert len(events) == 1
    assert "帐篷 A" in events[0].detail and "帐篷 B" in events[0].detail
    assert "2 项" in status


def test_market_rank_only_competitor_cheaper():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    own = _order("own", price=50)
    orders = {"abc": [_order("comp", price=40), _order("tie", price=50)]}
    events, status = market_rank_events([own], orders, now, labels={"abc": "测试物品"})
    assert len(events) == 1
    assert "测试物品" in events[0].detail and "40" in events[0].detail
    assert "1 单" in status
    assert market_rank_events([own], {"abc": [_order("tie", price=50)]}, now)[0] == []


def test_riven_price_is_strict_and_needs_buyout():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    rule = {
        "slug": "burston", "weapon": "伯斯顿", "positives": ["damage"],
        "negative": None, "price": 200,
    }
    def listing(id, cost):
        return {
            "id": id, "visible": True, "platform": "pc",
            "buyout_price": cost, "item": {
                "type": "riven", "weapon_url_name": "burston",
                "attributes": [{"url_name": "damage", "positive": True}],
            },
            "owner": {"ingame_name": "Alice"},
        }
    events, _ = riven_events([
        listing("good", 199), listing("equal", 200), listing("high", 500),
        listing("no-buyout", None),
    ], now, rule)
    assert len(events) == 1 and events[0].key == "riven-auction:good"


def test_store_transition_dedup_and_rearm(tmp_path):
    from nonebot_plugin_aawfcore.subscriptions.sources import Event
    now = datetime.now(UTC)
    store = SubscriptionStore(tmp_path / "sub.sqlite3")
    sub, _ = store.subscribe(
        "bot", "100", "200", "market_user", {"user": "alice"}
    )
    event = Event("market-rank:123", "卖单被压价", "详情", now, now)
    assert store.observe_changes(sub.id, [event], now, notify_initial=True) == 1
    assert store.observe_changes(sub.id, [event], now, notify_initial=True) == 0
    store.close()
    restored = SubscriptionStore(tmp_path / "sub.sqlite3")
    assert restored.observe_changes(sub.id, [event], now, notify_initial=True) == 0
    assert restored.observe_changes(sub.id, [], now, notify_initial=True) == 0
    assert restored.observe_changes(sub.id, [event], now, notify_initial=True) == 1
    restored.close()


@pytest.mark.asyncio
async def test_market_account_ingame_one_minute_poll(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=1)
    calls = []
    async def request(path):
        calls.append(path)
        if path.startswith("/user/"):
            return {"status": "ingame", "slug": "alice"}
        if path.startswith("/orders/user/"):
            return [_order("mine", price=80)]
        if path.startswith("/orders/itemId/"):
            return [_order("other", price=70)]
        raise AssertionError(path)
    market = SimpleNamespace(provider=SimpleNamespace(
        request=request,
        catalog=AsyncMock(return_value=Snapshot(data=[], source="test")),
    ))
    service = SubscriptionService(
        tmp_path, SimpleNamespace(fetch=AsyncMock()), market=market
    )
    service.store.subscribe("bot", "100", "200", "market_user", {"user": "alice"})
    await service._tick(now)
    pending = service.store.claim_due(now, {"bot"}, protocol="onebot")
    assert len(pending) == 1
    service.store.mark_sent(pending[0].id, now)
    assert calls.count("/orders/user/alice") == 1
    await service._tick(now + timedelta(seconds=30))
    assert calls.count("/orders/user/alice") == 1
    await service._tick(now + timedelta(minutes=1))
    assert calls.count("/orders/user/alice") == 2
    assert service.store.claim_due(now + timedelta(minutes=1), {"bot"}, protocol="onebot") == []
    await service.close()


@pytest.mark.asyncio
async def test_riven_watcher_baseline_then_new_auction(tmp_path, monkeypatch):
    now = datetime.now(UTC) + timedelta(minutes=1)
    rule = {"slug": "burston", "weapon": "伯斯顿",
            "positives": ["damage"], "negative": None, "price": 200}
    def listing(ident):
        return {
            "id": ident, "visible": True, "platform": "pc",
            "buyout_price": 150,
            "item": {"type": "riven", "weapon_url_name": "burston",
                     "attributes": [{"url_name": "damage", "positive": True}]},
            "owner": {"ingame_name": "Seller"},
        }
    rows = [listing("old")]
    provider = SimpleNamespace(search=AsyncMock(
        side_effect=lambda slug, query: Snapshot(data=list(rows), source="test")
    ))
    renderer = SimpleNamespace(render=AsyncMock(return_value=[b"image"]))
    service = SubscriptionService(
        tmp_path, SimpleNamespace(fetch=AsyncMock()),
        riven_market=SimpleNamespace(provider=provider), renderer=renderer,
    )
    service.store.subscribe("bot", "100", "200", "riven", rule)
    await service._tick(now)
    assert service.store.claim_due(now, {"bot"}, protocol="onebot") == []
    rows.append(listing("new"))
    later = now + timedelta(minutes=3)
    await service._tick(later)
    deliveries = service.store.claim_due(later, {"bot"}, protocol="onebot")
    assert len(deliveries) == 1
    message = await service.prepare_delivery(deliveries[0], later)
    assert any(segment.type == "image" for segment in message)
    await service.close()


def test_subscription_card_renders_with_notification_header():
    from nonebot_plugin_aawfcore.models.common import Card, Section
    from nonebot_plugin_aawfcore.rendering.renderer import CardRenderer

    renderer = CardRenderer()
    card = Card(
        title="发现新虚空裂缝", source="AAWarframe · 订阅提醒",
        sections=[Section(title="本次触发", rows=[["古纪生存", "虚空"]])],
    )
    rendered = renderer.html(card)
    assert "subscription-page" in rendered
    assert "订阅提醒" in rendered
    assert "古纪生存" in rendered
