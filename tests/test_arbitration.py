# 作用：验证仲裁边界、北京时间排期、类型筛选和人工记录持久化。
# 编写日期：2026-11-14
# 作者：Aameow

import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from nonebot_plugin_aawarframe.admin.server import create_app
from nonebot_plugin_aawarframe.initialization.nodes import parse_schedule
from nonebot_plugin_aawarframe.localization.resources import raw_mapping
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.services.arbitration import BEIJING, ArbitrationService

NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def service(tmp_path):
    nodes = raw_mapping("ExportRegions_zh.json")
    grq = SimpleNamespace(mapping=lambda _: copy.deepcopy(nodes))
    return ArbitrationService(grq, tmp_path)


def test_current_next_and_hour_rollover(service):
    board = service.query("arbitration", now=NOW).arbitration_board
    assert len(board.entries) == 2
    assert board.entries[0].time.timestamp() <= NOW.timestamp() < board.entries[1].time.timestamp()
    assert all(r.mission and r.faction for r in board.entries)
    next_board = service.query("arbitration", now=board.entries[1].time).arbitration_board
    assert next_board.entries[0].node_id == board.entries[1].node_id


def test_today_uses_beijing_day(service):
    now = datetime(2026, 11, 14, 17, tzinfo=timezone.utc)
    entries = service.query("today_arbitration", now=now).arbitration_board.entries
    assert len(entries) == 24
    assert [r.time.astimezone(BEIJING).hour for r in entries] == list(range(24))
    assert all(r.time.astimezone(BEIJING).date() == now.astimezone(BEIJING).date() for r in entries)


def test_filtered_and_s_tier_are_next_ten(service):
    survival = service.query("arbitration", "生存", NOW).arbitration_board.entries
    assert len(survival) == 10 and all(r.mission == "生存" and r.time > NOW for r in survival)
    efficient = service.query("efficient_arbitration", now=NOW).arbitration_board.entries
    assert len(efficient) == 10 and all(
        r.grade == "S" and r.vitus_per_minute == 0 for r in efficient
    )
    with pytest.raises(UserInputError):
        service.query("arbitration", "不存在的类型", NOW)
    with pytest.raises(UserInputError):
        service.query("today_arbitration", "参数", NOW)


def test_overrides_survive_reload_and_change_s_filter(service):
    key = service.query("efficient_arbitration", now=NOW).arbitration_board.entries[0].node_id
    service.save_node(key, "F", 2.5)
    assert all(
        r.node_id != key
        for r in service.query("efficient_arbitration", now=NOW).arbitration_board.entries
    )
    again = ArbitrationService(service.grq, service.path.parents[1])
    row = next(n for n in again.list_nodes() if n["id"] == key)
    assert row["arbitration"] == {"grade": "F", "vitus_per_minute": 2.5}
    with pytest.raises(ValueError):
        service.save_node(key, "S", float("nan"))
    outside = next(k for k, n in service.nodes.items() if n["arbitration"] is None)
    with pytest.raises(ValueError):
        service.save_node(outside, "S", 1)


def test_schedule_rejects_gaps_and_duplicates():
    with pytest.raises(ValueError):
        parse_schedule("3600,SolNode1\n10800,SolNode2")
    with pytest.raises(ValueError):
        parse_schedule("3600,SolNode1\n3600,SolNode2")


async def test_admin_requires_login_and_only_edits_arbitration_nodes(service):
    runtime = SimpleNamespace(
        grq=service.grq,
        arbitration=service,
        renderer=SimpleNamespace(cache=SimpleNamespace(entries={})),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime, "long-test-password-12345")),
        base_url="https://test",
    ) as client:
        assert (await client.get("/api/arbitration/nodes")).status_code == 401
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        rows = (await client.get("/api/arbitration/nodes")).json()["items"]
        assert len(rows) == 88
        assert (
            await client.put(
                "/api/arbitration/nodes",
                json={"node_id": rows[0]["id"], "grade": "S", "vitus_per_minute": 3},
            )
        ).status_code == 200
        assert (
            await client.put(
                "/api/arbitration/nodes",
                json={"node_id": "not-a-node", "grade": "S", "vitus_per_minute": 3},
            )
        ).status_code == 409
