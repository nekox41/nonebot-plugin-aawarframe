# 作用：验证午夜电波官方数据、时间边界、中文映射和命令分发。
# 编写日期：2026-11-11
# 作者：Aameow

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.nightwave import build_nightwave
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService
from nonebot_plugin_aawarframe.worldstate.parsers.common import ParseError


def recorded():
    path = Path(__file__).parent / "fixtures" / "nightwave-recorded.json"
    snapshot = Snapshot.model_validate_json(path.read_text())
    return snapshot, datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)


def test_recorded_tasks_translated_grouped_and_rendered():
    snapshot, now = recorded()
    card = build_nightwave(snapshot, now)
    assert card.nightwave_mode and card.status == DataStatus.OK and not card.notes
    assert [len(section.rows) for section in card.sections] == [3, 5, 2]
    assert card.sections[0].rows[0][0] == "制造者之触"
    assert card.sections[0].rows[0][4] == "今日新增"
    assert sum(row[4] == "今日新增" for row in card.sections[0].rows) == 1
    assert all(row[2] == "1,000" for row in card.sections[0].rows)
    assert all(row[2] == "4,500" for row in card.sections[1].rows)
    assert all(row[2] == "7,000" for row in card.sections[2].rows)
    assert sum(row[4] == "常驻" for row in card.sections[1].rows) == 3
    assert "|COUNT|" not in card.text() and "<DT_" not in card.text()
    assert "1500 米" in card.text() and "荧尘" in card.text()
    assert "/Lotus/" not in card.text()
    assert all(
        any("\u4e00" <= char <= "\u9fff" for char in row[1])
        for section in card.sections
        for row in section.rows
    )
    html = CardRenderer().html(card)
    assert "nightwave-page" in html and html.count('class="nightwave-task"') == 10
    assert "By. Aameow" in html


def test_active_time_boundaries_and_duplicate_tasks():
    snapshot, now = recorded()
    raw = snapshot.data["SeasonInfo"]
    task = deepcopy(raw["ActiveChallenges"][0])
    task["Activation"] = now.isoformat()
    task["Expiry"] = (now + timedelta(minutes=1)).isoformat()
    raw["ActiveChallenges"] = [task, deepcopy(task)]
    assert len(build_nightwave(snapshot, now).sections[0].rows) == 1
    assert build_nightwave(snapshot, now - timedelta(seconds=1)).status == DataStatus.EMPTY
    assert build_nightwave(snapshot, now + timedelta(minutes=1)).status == DataStatus.EMPTY


def test_unknown_and_malformed_task_does_not_hide_valid_tasks():
    snapshot, now = recorded()
    snapshot.data["SeasonInfo"]["ActiveChallenges"].append({"Challenge": "broken"})
    snapshot.data["SeasonInfo"]["ActiveChallenges"][0]["Challenge"] = (
        "/Lotus/Types/Challenges/Seasons/Daily/NewTask"
    )
    card = build_nightwave(snapshot, now)
    assert sum(len(section.rows) for section in card.sections) == 10
    assert card.notes and "NewTask" in card.text() and "/Lotus/" not in card.text()


def test_missing_inactive_or_empty_season():
    snapshot, now = recorded()
    snapshot.data["SeasonInfo"]["ActiveChallenges"] = []
    assert build_nightwave(snapshot, now).status == DataStatus.EMPTY
    snapshot.data["SeasonInfo"]["Expiry"] = now.isoformat()
    assert build_nightwave(snapshot, now).status == DataStatus.EMPTY
    snapshot.data["SeasonInfo"] = None
    assert build_nightwave(snapshot, now).status == DataStatus.EMPTY
    del snapshot.data["SeasonInfo"]
    with pytest.raises(ParseError):
        build_nightwave(snapshot, now)


async def test_command_registration_and_world_service(monkeypatch):
    registered = []
    monkeypatch.setattr(router, "register", lambda *args: registered.append(args))
    router.setup()
    assert ("午夜电波", {"电波"}, "nightwave") in registered
    snapshot, now = recorded()
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: now)
    provider = SimpleNamespace(fetch=AsyncMock(return_value=snapshot))
    card = await WorldStateService(provider).query("nightwave")
    assert card.nightwave_mode and card.status == DataStatus.OK
