# 作用：验证 worldstate 相关行为。
# 编写日期：2026-11-07
# 作者：Aameow

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from nonebot_plugin_aawarframe.infrastructure.http import HttpClient
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.models.worldstate import parse_date
from nonebot_plugin_aawarframe.providers.worldstate import WorldStateProvider
from nonebot_plugin_aawarframe.services.archimedea import build_archimedea
from nonebot_plugin_aawarframe.services.bounties import build_bounties
from nonebot_plugin_aawarframe.services.cetus import build_cetus
from nonebot_plugin_aawarframe.services.clan import build_clan
from nonebot_plugin_aawarframe.services.fissures import build_fissures
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService
from nonebot_plugin_aawarframe.worldstate.parsers.common import ParseError

NOW = datetime.fromtimestamp(1793923200, timezone.utc)


@pytest.mark.parametrize(
    "elapsed,phase", [(0, "白天"), (5999, "白天"), (6000, "黑夜"), (8999, "黑夜")]
)
def test_cetus_boundaries(worldstate, elapsed, phase):
    card = build_cetus(
        Snapshot(data=worldstate, source="fixture"), NOW + timedelta(seconds=elapsed)
    )
    assert card.cycle_items[0].state == phase
    assert len(card.sections[0].rows) == 5


def test_fissures_empty_unknown_and_expired(worldstate):
    snapshot = Snapshot(data=worldstate, source="fixture")
    assert len(build_fissures(snapshot, NOW).fissure_items) == 1
    unknown = build_fissures(snapshot, NOW, hard=True).text()
    assert "UnknownNode" in unknown and "NewTier" in unknown
    assert build_fissures(snapshot, NOW + timedelta(days=1)).status == DataStatus.EMPTY
    snapshot.data["ActiveMissions"] = []
    assert build_fissures(snapshot, NOW).status == DataStatus.EMPTY
    del snapshot.data["ActiveMissions"]
    with pytest.raises(ParseError):
        build_fissures(snapshot, NOW)


def test_invalid_record_does_not_discard_other_records(worldstate):
    worldstate["ActiveMissions"].append({"Node": "bad"})
    result = build_fissures(Snapshot(data=worldstate, source="fixture"), NOW)
    assert result.notes and result.fissure_items


def test_clan_rewards_are_immutable(worldstate):
    original = deepcopy(worldstate)
    snapshot = Snapshot(data=worldstate, source="fixture")
    assert build_clan(snapshot).sections[0].rows[0][:2] == ["Endo", "100"]
    assert build_clan(snapshot).sections[0].rows[0][:2] == ["Endo", "100"]
    assert worldstate == original


def test_archimedea_and_bounties(worldstate):
    snapshot = Snapshot(data=worldstate, source="fixture")
    assert "UnknownDeviation" in build_archimedea(snapshot, "CT_LAB").text()
    assert "炽蛇军" in build_archimedea(snapshot, "CT_HEX").text()
    snapshot.data["SyndicateMissions"][0]["Jobs"][0]["xpAmounts"] = [100, 100, 100]
    bounties = build_bounties(snapshot, NOW, 1)
    assert bounties.bounty_items[0].stages == 3
    assert bounties.bounty_items[0].rewards


async def test_service_isolates_parser_failures(worldstate, monkeypatch):
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: NOW)
    del worldstate["Conquests"]
    provider = SimpleNamespace(
        fetch=AsyncMock(return_value=Snapshot(data=worldstate, source="fixture"))
    )
    service = WorldStateService(provider)
    assert (await service.query("deep")).status == DataStatus.PARSE_ERROR
    assert (await service.query("fissures")).status == DataStatus.OK
    provider.fetch.reset_mock()
    assert (await service.query("arbitration")).status == DataStatus.UNAVAILABLE
    provider.fetch.assert_not_awaited()


async def test_provider_shared_snapshot_and_persistence(worldstate, tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=worldstate)

    http = HttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    provider = WorldStateProvider(http, tmp_path)
    first, second = await provider.fetch(), await provider.fetch()
    assert len(requests) == 1 and first.fetched_at == second.fetched_at
    assert (tmp_path / "worldstate-latest.json").exists()
    await provider.close()
    await http.close()


@pytest.mark.parametrize(
    "value", ["2026-11-06T00:00:00Z", 1793923200, {"$date": {"$numberLong": "1793923200000"}}]
)
def test_world_dates(value):
    assert parse_date(value) == NOW


@pytest.mark.parametrize(
    "feature", ["cetus", "fissures", "steel_fissures", "deep", "temporal", "bounties", "clan"]
)
async def test_recorded_official_worldstate(feature, monkeypatch):
    import json
    from pathlib import Path

    recorded = json.loads((Path(__file__).parent / "fixtures/worldstate-recorded.json").read_text())
    snapshot = Snapshot.model_validate(recorded)
    now = datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)
    monkeypatch.setattr("nonebot_plugin_aawarframe.services.worldstate.utcnow", lambda: now)
    provider = SimpleNamespace(fetch=AsyncMock(return_value=snapshot))
    card = await WorldStateService(provider).query(feature)
    assert card.status == DataStatus.OK
    assert (
        card.bounty_items
        or card.fissure_items
        or card.cycle_items
        or sum(len(section.rows) for section in card.sections) > 0
    )
    assert not card.notes
