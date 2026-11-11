# 作用：校验三地赏金的种子还原、奖励详情和命令分发。
# 编写日期：2026-11-10
# 作者：Aameow

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.localization.resolver import load_mapping
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.models.errors import UserInputError
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.bounties import BOUNTY_REGIONS, build_bounties
from nonebot_plugin_aawarframe.worldstate.parsers.challenge_bounties import (
    generate_challenge_bounties,
)
from nonebot_plugin_aawarframe.worldstate.seeded_random import SeededRandom

FIXTURES = Path(__file__).parent / "fixtures"


def recorded():
    snapshot = Snapshot.model_validate_json(
        (FIXTURES / "challenge-bounties-recorded.json").read_text()
    )
    return snapshot, datetime.fromtimestamp(snapshot.data["Time"], timezone.utc)


@pytest.mark.parametrize("region", ["sanctum", "zariman", "hex"])
def test_seed_generation_matches_independent_public_reference(region):
    data = load_mapping("challenge_bounties.json")
    before = deepcopy(data)
    reference = json.loads((FIXTURES / "challenge-bounties-reference.json").read_text())
    agents = list(data["allies"].values()) if region == "hex" else None
    generated = generate_challenge_bounties(data["manifests"][region], reference["seed"], agents)
    assert generated == reference["response"]["bounties"][BOUNTY_REGIONS[region].syndicate]
    assert data == before  # 不能让洗牌污染下一次查询的缓存配置。
    assert (
        generate_challenge_bounties(data["manifests"][region], reference["seed"], agents)
        == generated
    )


@pytest.mark.parametrize("region,count", [("sanctum", 5), ("zariman", 5), ("hex", 7)])
def test_overview_and_each_completion_reward(region, count):
    snapshot, now = recorded()
    card = build_bounties(snapshot, now, region=region)
    assert card.bounty_challenge_mode and card.title == BOUNTY_REGIONS[region].title
    assert len(card.bounty_items) == count and not card.notes
    assert not card.bounty_locations
    for index, job in enumerate(card.bounty_items, 1):
        assert job.objectives and not any("|" in line for line in job.objectives)
        detail = build_bounties(snapshot, now, index, region=region)
        selected = detail.bounty_items[0]
        assert selected.rewards and selected.reward_labels == ["完成奖励"]
        assert all(len(row.chances) == 1 for row in selected.rewards)
        assert 0.999 <= sum(row.chances[0] for row in selected.rewards) <= 1.001
        html = CardRenderer().html(detail)
        assert "完成奖励" in html and "阶段 5" not in html and "尚未收录" not in html
    if region == "zariman":
        assert card.bounty_currency == "虚空刺翎"
        assert [job.standing for job in card.bounty_items] == [1, 2, 3, 4, 5]
        assert {job.faction for job in card.bounty_items} == {"Corpus"}
    if region == "hex":
        assert len({job.ally for job in card.bounty_items[:6]}) == 6
        assert card.bounty_items[-1].kind == "杀毒" and not card.bounty_items[-1].ally
    assert (
        build_bounties(snapshot, now + timedelta(days=1), region=region).status == DataStatus.EMPTY
    )
    with pytest.raises(UserInputError, match=card.title):
        build_bounties(snapshot, now, count + 1, region=region)


async def test_new_bounty_commands_dispatch_index_and_render_errors(monkeypatch):
    snapshot, now = recorded()
    renderer = SimpleNamespace(render=AsyncMock(return_value=[b"webp"]))
    world = SimpleNamespace(
        query=AsyncMock(return_value=build_bounties(snapshot, now, region="hex"))
    )
    monkeypatch.setattr(
        router, "get_runtime", lambda: SimpleNamespace(world=world, renderer=renderer)
    )
    for feature in ["sanctum_bounties", "zariman_bounties", "hex_bounties"]:
        result = await router.dispatch(feature, "2")
        world.query.assert_awaited_with(feature, bounty_index=2)
        assert [segment.type for segment in result] == ["image"]
        result = await router.dispatch(feature, "0")
        assert [segment.type for segment in result] == ["image"]
    registered = []
    monkeypatch.setattr(router, "register", lambda *args: registered.append(args))
    router.setup()
    assert ("圣所赏金", set(), "sanctum_bounties") in registered
    assert ("扎里曼赏金", set(), "zariman_bounties") in registered
    assert ("1999赏金", set(), "hex_bounties") in registered


def test_single_candidate_does_not_advance_random_state():
    random = SeededRandom(51369)
    assert random.choice(["only"]) == "only" and random.seed == 51369
