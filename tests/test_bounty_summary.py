# Desc: 记录赏金汇总和命令别名的预期行为。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime, timezone
from pathlib import Path

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import Snapshot
from nonebot_plugin_aawarframe.services.bounties import build_bounties, build_bounty_summary


def test_commands_and_aliases(monkeypatch):
    registered = {}
    monkeypatch.setattr(
        router,
        "register",
        lambda name, aliases, feature: registered.update(
            {key: feature for key in (name, *aliases)}
        ),
    )
    router.setup()
    assert "夜灵" not in registered and "王境" not in registered
    assert registered["平原"] == "plains"
    assert registered["赏金"] == "bounty_summary"
    for name in ("地球", "金星", "火卫二"):
        assert registered[name] == registered[name + "赏金"]


def test_summary_selection():
    fixture = Path(__file__).parent / "fixtures" / "challenge-bounties-recorded.json"
    snapshot = Snapshot.model_validate_json(fixture.read_text())
    now = datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)
    card = build_bounty_summary(snapshot, now)
    earth = build_bounties(snapshot, now)
    assert card.sections[0].rows == [
        [key, "\n".join(value)] for key, value in earth.bounty_locations.items()
    ]
    for section, region in zip(card.sections[1:], ("sanctum", "zariman", "hex")):
        source = build_bounties(snapshot, now, region=region)
        expected = [
            job.index
            for job in source.bounty_items
            if job.index in {4, 5} or (region == "hex" and job.kind == "杀毒")
        ]
        assert [int(row[0].split(".")[0]) for row in section.rows] == expected


def test_summary_earth_tents():
    fixture = Path(__file__).parent / "fixtures" / "bounties-recorded.json"
    snapshot = Snapshot.model_validate_json(fixture.read_text())
    now = datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)
    card = build_bounty_summary(snapshot, now)
    assert len(card.sections[0].rows) == 3
    assert {row[0] for row in card.sections[0].rows} == {"帐篷 A", "帐篷 B", "帐篷 C"}
