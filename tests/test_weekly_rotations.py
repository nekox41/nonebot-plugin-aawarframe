# 作用：验证周奖励、日历、回廊选项与边界轮换，确保下期信息准确。
# 编写日期：2026-11-11
# 作者：Aameow

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.calendar import build_calendar
from nonebot_plugin_aawarframe.services.circuit import build_circuit, rotation_index
from nonebot_plugin_aawarframe.services.clan import build_clan
from nonebot_plugin_aawarframe.services.steel_path import build_steel_path
from nonebot_plugin_aawarframe.services.weekly import week_bounds
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService


def recorded():
    path = Path(__file__).parent / "fixtures" / "weekly-rotations-recorded.json"
    snapshot = Snapshot.model_validate_json(path.read_text())
    return snapshot, datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)


def test_clan_both_weeks_points_and_credit_bundle():
    snapshot, now = recorded()
    card = build_clan(snapshot, now)
    assert len(card.sections) == 2
    assert "赤毒要塞" in card.sections[0].title and "木星" in card.sections[1].title
    assert ["现金", "100,000", "1,500"] in card.sections[0].rows
    assert ["Endo", "5,000", "2,000"] in card.sections[1].rows
    assert "/Lotus/" not in card.text()


def test_calendar_all_tasks_and_reward_choices():
    snapshot, now = recorded()
    card = build_calendar(snapshot, now)
    assert [s.title for s in card.sections] == ["10 月", "11 月", "12 月"]
    rows = [row for s in card.sections for row in s.rows]
    assert len(rows) == 12
    assert sum(row[1] == "任务" for row in rows) == 6
    assert sum(row[1] == "奖励 · 二选一" for row in rows) == 6
    assert rows[0] == ["10-08", "任务", "使用技能击杀 100 名科腐者"]
    assert "紫晶执刑官源力石" in card.text()
    assert "/Lotus/" not in card.text()


def test_circuit_current_and_next_are_verified_by_live_choices():
    snapshot, now = recorded()
    card = build_circuit(snapshot, now)
    assert "Nidus / Octavia / Harrow" == card.sections[0].rows[0][1]
    assert "Gara / Khora / Revenant" == card.sections[0].rows[1][1]
    assert "野猪" in card.sections[1].rows[0][1]
    incarnons = build_circuit(snapshot, now, all_incarnons=True)
    section = incarnons.sections[0]
    assert len(section.rows) == 9 and section.highlighted_rows == [1]
    assert "本周" in section.rows[1][0]
    html = CardRenderer().html(incarnons)
    assert html.count('class="weekly-current"') == 1
    assert rotation_index(["Boar", "New Weapon"], [["Boar", "Gammacor"]]) is None
    snapshot.data["EndlessXpSchedule"][0]["CategoryChoices"][1]["Choices"] = ["New Weapon"]
    changed = build_circuit(snapshot, now)
    assert changed.sections[1].rows[1][1] == "下期轮换暂时无法确认"


def test_fixed_steel_rotation_wrap_and_reset_boundary():
    snapshot, now = recorded()
    epoch = datetime(2020, 11, 16, tzinfo=timezone.utc)
    card = build_steel_path(snapshot, epoch)
    assert card.sections[0].rows[0] == ["Umbra Forma 蓝图", "150"]
    assert card.sections[1].rows[0] == ["50,000 赤毒", "55"]
    last = build_steel_path(snapshot, epoch + timedelta(weeks=7))
    assert last.sections[1].rows[0] == ["Umbra Forma 蓝图", "150"]
    start, end = week_bounds(now)
    assert start.weekday() == 0 and end - start == timedelta(days=7)
    before = build_steel_path(snapshot, end - timedelta(microseconds=1))
    after = build_steel_path(snapshot, end)
    assert before.sections[1].rows == after.sections[0].rows


@pytest.mark.parametrize("feature", ["clan", "calendar", "circuit", "incarnons", "steel_path"])
async def test_world_query_and_commands(monkeypatch, feature):
    snapshot, now = recorded()
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: now)
    service = WorldStateService(SimpleNamespace(fetch=AsyncMock(return_value=snapshot)))
    card = await service.query(feature)
    assert card.weekly_mode and card.status == DataStatus.OK and not card.notes
    registered = []
    monkeypatch.setattr(router, "register", lambda *args: registered.append(args))
    router.setup()
    assert ("氏族", {"氏族奖励"}, "clan") in registered
    assert ("午夜电波", {"电波"}, "nightwave") in registered
    for name in ("日历", "钢精", "回廊", "灵化"):
        assert any(row[0] == name for row in registered)


def test_empty_expired_schedule_does_not_predict_stale_choices():
    snapshot, now = recorded()
    _, end = week_bounds(now)
    assert build_calendar(snapshot, end).status == DataStatus.EMPTY
    assert build_circuit(snapshot, end).status == DataStatus.EMPTY


async def test_steel_rotation_is_available_without_worldstate():
    provider = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("offline")))
    card = await WorldStateService(provider).query("steel_path")
    assert card.weekly_mode and card.status == DataStatus.OK
    provider.fetch.assert_not_awaited()
