"""局部可回收订阅编号、旧版 SQLite 迁移与多列图片清单。"""

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawfcore.subscriptions.service import SubscriptionService
from nonebot_plugin_aawfcore.subscriptions.store import SubscriptionStore


def test_reuse_smallest_available_number_without_reusing_primary_key(tmp_path):
    store = SubscriptionStore(tmp_path / "subscriptions.sqlite3")
    scope = ("bot", "group", "user")
    created = [
        store.subscribe(*scope, "fissure", {"mode": "normal", "mission": str(i)})[0]
        for i in range(5)
    ]
    assert [sub.number for sub in created] == [1, 2, 3, 4, 5]
    assert len({sub.id for sub in created}) == 5
    assert store.remove_number(2, *scope)
    assert not store.remove_number(2, *scope)
    assert [sub.number for sub in store.list_for(*scope)] == [1, 3, 4, 5]
    replacement, fresh = store.subscribe(
        *scope, "fissure", {"mode": "steel", "mission": "生存"}
    )
    assert fresh and replacement.number == 2
    assert replacement.id > max(sub.id for sub in created)
    assert [sub.number for sub in store.list_for(*scope)] == [1, 2, 3, 4, 5]
    # 本范围内已有编号 2，不影响另外群或另外用户使用编号 2。
    assert store.subscribe("bot", "group2", "user")[0].number == 1
    assert store.subscribe("bot", "group", "other")[0].number == 1
    assert store.subscribe("bot2", "group", "user")[0].number == 1
    assert not store.remove_number(2, "bot", "group2", "user")
    store.close()

    reopened = SubscriptionStore(tmp_path / "subscriptions.sqlite3")
    assert [(s.number, s.id) for s in reopened.list_for(*scope)] == [
        (1, created[0].id),
        (2, replacement.id),
        (3, created[2].id),
        (4, created[3].id),
        (5, created[4].id),
    ]
    reopened.close()


def test_upgrade_existing_autoincrement_ids_and_preserve_delivery_links(tmp_path):
    """兼容旧数据库：保留内部 ID，按所在群和用户分配 1..N 小编号。"""
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                rule_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(bot_id,group_id,user_id,kind,rule_json)
            )
        """)
        for ident, group, user, kind in [
            (21, "g1", "u", "aya"),
            (149, "g1", "u", "arbitration"),
            (501, "g2", "u", "aya"),
            (502, "g1", "v", "aya"),
        ]:
            db.execute(
                "INSERT INTO subscriptions "
                "(id,bot_id,group_id,user_id,kind,rule_json,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (ident, "bot", group, user, kind, "{}", 1763400000.0),
            )
    store = SubscriptionStore(path)
    scope = ("bot", "g1", "u")
    assert [(s.id, s.number) for s in store.list_for(*scope)] == [
        (21, 1), (149, 2)
    ]
    assert store.list_for("bot", "g2", "u")[0].number == 1
    assert store.list_for("bot", "g1", "v")[0].number == 1
    now = datetime.now(timezone.utc)
    store.enqueue(149, "legacy:event", now, now)
    assert store.remove_number(1, *scope)
    new, _ = store.subscribe(*scope, "cetus_night", {})
    assert new.number == 1 and new.id > 502
    assert store.db.execute(
        "SELECT subscription_id FROM subscription_deliveries "
        "WHERE event_key='legacy:event'"
    ).fetchone()[0] == 149
    store.close()
    migrated = SubscriptionStore(path)
    assert [(s.number, s.id) for s in migrated.list_for(*scope)] == [
        (1, new.id), (2, 149)
    ]
    migrated.close()


@pytest.mark.asyncio
async def test_public_numbers_commands_and_three_column_list(tmp_path):
    provider = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("offline")))
    service = SubscriptionService(tmp_path, provider)
    scope = ("bot", "100", "200")
    first = await service.handle("subscribe", "夜灵", scope)
    second = await service.handle("subscribe", "仲裁", scope)
    third = await service.handle("subscribe", "阿耶", scope)
    assert "编号 1" in first and "编号 2" in second and "编号 3" in third
    assert "已取消订阅 #2。" == await service.handle("unsubscribe", "2", scope)
    new = await service.handle("subscribe", "九重天", scope)
    assert "编号 2" in new
    listed = await service.handle("list_subscriptions", "", scope)
    assert "等待检查" not in listed and "状态" not in listed
    assert "#1 夜灵平野" in listed
    assert "#2 九重天" in listed
    assert "#3 阿耶" in listed
    card = service.list_card(scope)
    assert card is not None
    assert card.title == "我的订阅"
    assert card.sections[0].columns == ["订阅", "订阅", "订阅"]
    assert card.sections[0].rows == [[
        "#1 夜灵平野 · 黑夜前 15 分钟",
        "#2 九重天",
        "#3 阿耶 · 地球三帐篷",
    ]]
    assert not service.store.remove_number(2, "bot", "100", "someone-else")
    await service.close()


@pytest.mark.asyncio
async def test_router_my_subscriptions_sends_image_with_three_columns(tmp_path, monkeypatch):
    from nonebot_plugin_aawfcore.commands import router

    provider = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("offline")))
    service = SubscriptionService(tmp_path, provider)
    scope = ("bot", "100", "200")
    service.store.subscribe(*scope, "arbitration", {})
    service.store.subscribe(*scope, "aya", {})
    service.store.subscribe(*scope, "fissure", {
        "mode": "steel", "planet": "塞德娜", "mission": "生存", "tier": "古纪",
    })
    service.store.subscribe(*scope, "fissure", {
        "mode": "normal", "planet": "虚空", "mission": "", "tier": "",
    })
    renderer = SimpleNamespace(render=AsyncMock(return_value=[b"fake-image"]))
    monkeypatch.setattr(
        router, "get_runtime",
        lambda: SimpleNamespace(subscriptions=service, renderer=renderer),
    )
    output = await router.dispatch("list_subscriptions", "", subscriber=scope)
    assert [segment.type for segment in output] == ["image"]
    card = renderer.render.await_args.args[0]
    assert len(card.sections[0].rows) == 2
    assert len(card.sections[0].rows[0]) == 3
    assert len(card.sections[0].rows[1]) == 3
    assert card.sections[0].rows[1][1:] == ["", ""]
    assert not any("等待" in cell for row in card.sections[0].rows for cell in row)

    renderer.render.side_effect = RuntimeError("browser offline")
    output = await router.dispatch("list_subscriptions", "", subscriber=scope)
    assert [segment.type for segment in output] == ["text"]
    assert "#1" in output.extract_plain_text()
    assert "状态" not in output.extract_plain_text()

    await service.close()
