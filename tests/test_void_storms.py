# Desc: 记录九重天裂缝的预期行为。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.services.fissures import build_fissures, build_void_storms
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


def storm(node="CrewBattleNode519", tier="VoidT1", *, start=NOW, end=NOW + timedelta(hours=1)):
    return {
        "Node": node,
        "ActiveMissionTier": tier,
        "Activation": {"$date": {"$numberLong": str(int(start.timestamp() * 1000))}},
        "Expiry": {"$date": {"$numberLong": str(int(end.timestamp() * 1000))}},
    }


def test_storm_tier_source_localization_and_sorting(worldstate):
    worldstate["VoidStorms"] = [storm(tier="VoidT3"), {**storm(), "Modifier": "VoidT6"}]
    snapshot = Snapshot(data=worldstate, source="official", stale=True)
    card = build_void_storms(snapshot, NOW)
    rows = card.fissure_items
    assert [row.tier for row in rows] == ["古纪", "中纪"]
    assert (rows[0].node, rows[0].planet) == ("克姆地带", "地球比邻星域")
    assert (rows[0].mission, rows[0].faction) == ("前哨战", "Grineer")
    assert rows[0].remaining == "1 小时 0 分 0 秒"
    assert card.stale and card.source == snapshot.source and card.fetched_at == snapshot.fetched_at
    assert len(build_fissures(snapshot, NOW).fissure_items) == 1


def test_storm_unknown_values_and_partial_failure():
    snapshot = Snapshot(
        data={"VoidStorms": [storm("UnknownNode", "FutureTier"), {"Node": "bad"}]},
        source="official",
    )
    card = build_void_storms(snapshot, NOW)
    assert len(card.fissure_items) == 1
    assert "UnknownNode" in card.text() and "FutureTier" in card.text()
    assert card.notes and card.status == DataStatus.OK


def test_storm_activation_expiry_boundaries():
    snapshot = Snapshot(
        data={"VoidStorms": [storm(), storm(start=NOW + timedelta(seconds=1)), storm(end=NOW)]},
        source="official",
    )
    card = build_void_storms(snapshot, NOW)
    assert len(card.fissure_items) == 1
    assert build_void_storms(snapshot, NOW + timedelta(hours=2)).status == DataStatus.EMPTY
    assert (
        build_void_storms(Snapshot(data={"VoidStorms": []}, source="official"), NOW).status
        == DataStatus.EMPTY
    )


@pytest.mark.parametrize("value", [None, {}, [{"Node": "bad"}]])
async def test_storm_parse_failure_does_not_affect_regular_fissures(value, worldstate, monkeypatch):
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: NOW)
    worldstate["VoidStorms"] = value
    provider = SimpleNamespace(
        fetch=AsyncMock(return_value=Snapshot(data=worldstate, source="official"))
    )
    service = WorldStateService(provider)
    assert (await service.query("railjack_fissures")).status == DataStatus.PARSE_ERROR
    assert (await service.query("fissures")).status == DataStatus.OK


async def test_missing_storm_field_is_not_reported_as_empty(worldstate):
    provider = SimpleNamespace(
        fetch=AsyncMock(return_value=Snapshot(data=worldstate, source="official"))
    )
    assert (
        await WorldStateService(provider).query("railjack_fissures")
    ).status == DataStatus.PARSE_ERROR


def test_railjack_command_alias(monkeypatch):
    registered = []
    monkeypatch.setattr(router, "register", lambda *args: registered.append(args))
    router.setup()
    assert ("九重天", {"九重天裂缝"}, "railjack_fissures") in registered


async def test_recorded_official_void_storms(monkeypatch):
    import json
    from pathlib import Path

    recorded = json.loads((Path(__file__).parent / "fixtures/voidstorms-recorded.json").read_text())
    snapshot = Snapshot.model_validate(recorded)
    now = datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: now)
    provider = SimpleNamespace(fetch=AsyncMock(return_value=snapshot))
    card = await WorldStateService(provider).query("railjack_fissures")
    assert card.status == DataStatus.OK
    assert len(card.fissure_items) == len(snapshot.data["VoidStorms"])
    assert not card.notes
