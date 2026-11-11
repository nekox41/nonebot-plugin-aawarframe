# 作用：验证地球赏金概览、五阶段奖励及作者统计任务池。
# 编写日期：2026-11-07
# 作者：Aameow

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.commands.parsing import parse_bounty_index
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.bounties import build_bounties
from nonebot_plugin_aawarframe.worldstate.parsers.bounties import parse_rewards
from nonebot_plugin_aawarframe.worldstate.parsers.location_bounties import location_bounties


def test_tents_share_seed_and_only_appear_in_overview():
    snapshot, now = recorded()
    card = build_bounties(snapshot, now)
    assert card.bounty_locations == location_bounties(21461)
    assert set(card.bounty_locations) == {"帐篷 A", "帐篷 B", "帐篷 C"}
    assert all(len(jobs) == len(set(jobs)) == 3 for jobs in card.bounty_locations.values())
    assert len({tuple(jobs) for jobs in card.bounty_locations.values()}) > 1
    assert not build_bounties(snapshot, now, 1).bounty_locations
    html = CardRenderer().html(card)
    assert html.count('class="bounty-location"') == 3
    for mission in snapshot.data["SyndicateMissions"]:
        mission.pop("Seed", None)
    missing = build_bounties(snapshot, now)
    assert not missing.bounty_locations and len(missing.bounty_items) == 7


def recorded():
    raw = json.loads((Path(__file__).parent / "fixtures/worldstate-recorded.json").read_text())
    snapshot = Snapshot.model_validate(raw)
    return snapshot, datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)


def test_overview_contains_only_task_level_and_standing():
    snapshot, now = recorded()
    card = build_bounties(snapshot, now)
    assert len(card.bounty_items) == 7
    first = card.bounty_items[0]
    assert first.standing == 1080 and first.min_level == 5 and first.max_level == 15
    assert all(not job.rewards and not job.task_pools for job in card.bounty_items)
    html = CardRenderer().html(card)
    assert 'class="bounty-overview"' in html and html.count('class="bounty-refresh"') == 1
    assert 'class="bounty-rewards"' not in html and 'class="bounty-pool"' not in html
    assert "1080" in html and "破坏原型机" in html


def test_detail_uses_five_stage_reference_and_author_task_list():
    snapshot, now = recorded()
    card = build_bounties(snapshot, now, 1)
    job = card.bounty_items[0]
    assert card.bounty_detail and job.index == 1
    assert job.stages == 3  # 保留官方实际阶段数，展示按用户要求使用五阶段参考。
    assert len(job.task_pools) == 5 and job.task_pools[-1] == ["破坏补给"]
    assert "消灭一定数量的敌人（洞穴）" in job.task_pools[3]
    assert all(len(reward.chances) == 5 for reward in job.rewards)
    html = CardRenderer().html(card)
    assert "阶段 5" in html and "五阶段可能任务池" in html
    assert "对应关系待确认" not in html


def test_unknown_reward_pool_does_not_discard_other_jobs_or_task_pool():
    snapshot, now = recorded()
    cetus = next(m for m in snapshot.data["SyndicateMissions"] if m["Tag"] == "CetusSyndicate")
    cetus["Jobs"][0]["rewards"] = "UnknownRewards"
    assert len(build_bounties(snapshot, now).bounty_items) == 7
    detail = build_bounties(snapshot, now, 1).bounty_items[0]
    assert not detail.rewards and detail.message and len(detail.task_pools) == 5
    assert build_bounties(snapshot, now, 2).bounty_items[0].rewards


def test_narmer_does_not_reuse_unverified_regular_task_pool():
    snapshot, now = recorded()
    job = build_bounties(snapshot, now, 7).bounty_items[0]
    assert job.kind == "合一众" and job.rewards
    assert not job.task_pools and "尚未收录" in job.task_pool_note


def test_expired_cycle_is_empty_and_job_number_is_validated():
    snapshot, now = recorded()
    from datetime import timedelta

    assert build_bounties(snapshot, now + timedelta(days=1)).status == DataStatus.EMPTY
    with pytest.raises(UserInputError):
        build_bounties(snapshot, now, 8)
    assert parse_bounty_index("") is None and parse_bounty_index(" 2 ") == 2
    for value in ["0", "-1", "1 extra", "一", "100"]:
        with pytest.raises(UserInputError):
            parse_bounty_index(value)


def test_reward_stage_mapping_and_missing_probability():
    pools = [
        [{"type": "a", "name": "A", "itemCount": 1, "probability": 0.2}],
        [{"type": "b", "name": "B", "itemCount": 2, "probability": 0.3}],
        [{"type": "a", "name": "A", "itemCount": 1, "probability": 0.4}],
        [{"type": "a", "name": "A", "itemCount": 1, "probability": 0.5}],
    ]
    rows = parse_rewards(pools, 5)
    assert rows[0].chances == [0.2, None, None, 0.4, 0.5]
    assert rows[1].chances == [None, 0.3, 0.3, None, None]


def test_cetus_alias_is_removed(monkeypatch):
    registered = []
    monkeypatch.setattr(router, "register", lambda *args: registered.append(args))
    router.setup()
    assert ("地球赏金", {"地球"}, "bounties") in registered
    assert not any(name == "希图斯" or "希图斯" in aliases for name, aliases, _ in registered)


@pytest.mark.parametrize(
    "region,title,count,locations",
    [
        ("venus", "金星赏金", 7, 7),
        ("deimos", "火卫二赏金", 9, 5),
    ],
)
def test_other_worlds_include_localized_jobs_locations_and_details(region, title, count, locations):
    raw = (Path(__file__).parent / "fixtures/bounties-recorded.json").read_text()
    snapshot = Snapshot.model_validate_json(raw)
    now = datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)
    card = build_bounties(snapshot, now, region=region)
    assert card.title == title and len(card.bounty_items) == count
    assert len(card.bounty_locations) == locations
    assert all(len(jobs) == len(set(jobs)) == 3 for jobs in card.bounty_locations.values())
    assert all(
        "Bounty" not in name and "Job" not in name
        for jobs in card.bounty_locations.values()
        for name in jobs
    )
    assert not card.notes
    for index in range(1, count + 1):
        detail = build_bounties(snapshot, now, index, region=region)
        job = detail.bounty_items[0]
        assert job.rewards and not job.message
        assert all(len(reward.chances) == len(job.reward_labels) for reward in job.rewards)
        assert not detail.bounty_locations
        if job.kind == "隔离库":
            assert job.reward_labels == ["完成奖励"] and not job.task_pools
        elif job.kind == "无尽":
            assert len(job.task_pools) == len(job.reward_labels) == 3
        elif job.kind != "合一众":
            assert len(job.task_pools) == 5
    assert (card.bounty_currency == "母亲石印") == (region == "deimos")
    if region == "deimos":
        assert {"地下区域 A", "地下区域 B", "地下区域 C"} <= card.bounty_locations.keys()
    html = CardRenderer().html(card)
    assert card.bounty_region in html and html.count('class="bounty-location"') == locations
    assert parse_bounty_index("2", title) == 2
    with pytest.raises(UserInputError, match=title):
        parse_bounty_index("0", title)
