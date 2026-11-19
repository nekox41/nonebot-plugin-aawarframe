# 作用：验证科研轮换筛选、难度差异、中文变量和图片内容。
# 编写日期：2026-11-11
# 作者：Aameow

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.archimedea import build_archimedea
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService


def recorded():
    path = Path(__file__).parent / "fixtures" / "worldstate-recorded.json"
    snapshot = Snapshot.model_validate_json(path.read_text())
    return snapshot, datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)


@pytest.mark.parametrize("kind,title", [("CT_LAB", "深层科研"), ("CT_HEX", "时光科研")])
def test_recorded_research_conditions_and_localization(kind, title):
    snapshot, now = recorded()
    card = build_archimedea(snapshot, kind, now)
    assert card.title == title and card.archimedea_mode
    assert len(card.sections) == 4
    assert card.archimedea_activation < now < card.archimedea_expiry
    for section in card.sections[:3]:
        assert [row[0] for row in section.rows] == ["偏差", "风险", "精英风险"]
    assert len(card.sections[-1].rows) == 4
    assert "/Lotus/" not in card.text() and "|val|" not in card.text()
    assert "InfectedWounds" not in card.text() and "DullBlades" not in card.text()
    html = CardRenderer().html(card)
    assert "research-tag--elite" in html and "By. Aameow" in html
    assert "刷新" in html


def test_select_active_rotation_and_handle_expired_or_future():
    snapshot, now = recorded()
    current = deepcopy(snapshot.data["Conquests"][0])
    future = deepcopy(current)
    future["Activation"] = (now + timedelta(days=1)).isoformat()
    future["Expiry"] = (now + timedelta(days=8)).isoformat()
    snapshot.data["Conquests"].insert(0, future)
    assert build_archimedea(snapshot, "CT_LAB", now).archimedea_activation < now
    expiry = build_archimedea(snapshot, "CT_LAB", now).archimedea_expiry
    snapshot.data["Conquests"] = [current]
    assert build_archimedea(snapshot, "CT_LAB", expiry).status == DataStatus.EMPTY


def test_differing_difficulties_and_unknown_translations():
    snapshot, now = recorded()
    mission = snapshot.data["Conquests"][0]["Missions"][0]
    mission["difficulties"][1]["deviation"] = "NewDeviation"
    mission["difficulties"][1]["risks"] = ["NewRisk"]
    snapshot.data["Conquests"][0]["Variables"] = ["DullBlades", "NoPetsAllowed", "NewVariable"]
    card = build_archimedea(snapshot, "CT_LAB", now)
    assert [row[0] for row in card.sections[0].rows] == [
        "普通偏差",
        "精英偏差",
        "普通风险",
        "精英风险",
    ]
    assert ["精英偏差", "NewDeviation", "说明暂缺"] in card.sections[0].rows
    assert card.sections[-1].rows[0][1] == "钝重兵刃"
    assert card.sections[-1].rows[1][1] == "禁止同伴"
    assert "/Lotus/" not in card.text()


def test_partial_mission_keeps_original_number():
    snapshot, now = recorded()
    snapshot.data["Conquests"][0]["Missions"][0] = {"invalid": True}
    card = build_archimedea(snapshot, "CT_LAB", now)
    assert card.sections[0].title == "任务 1"
    assert card.sections[1].title.startswith("2.")
    assert card.notes


@pytest.mark.parametrize("feature,kind", [("deep", "CT_LAB"), ("temporal", "CT_HEX")])
async def test_world_service_routes_research(monkeypatch, feature, kind):
    snapshot, now = recorded()
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: now)
    provider = SimpleNamespace(fetch=AsyncMock(return_value=snapshot))
    card = await WorldStateService(provider).query(feature)
    assert card.text() == build_archimedea(snapshot, kind, now).text()
