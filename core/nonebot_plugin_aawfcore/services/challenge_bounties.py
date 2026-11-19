# 作用：整理圣所、扎里曼和 1999 赏金的任务条件、固定奖励与完成奖励。
# 编写日期：2026-11-10
# 作者：Aameow

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from ..localization.resolver import load_mapping
from ..models.bounties import BountyDisplay
from ..models.common import Card, DataStatus, Snapshot
from ..models.errors import UserInputError
from ..models.worldstate import SyndicateMission
from ..worldstate.parsers.bounties import merge_reward_pools
from ..worldstate.parsers.challenge_bounties import generate_challenge_bounties
from ..worldstate.parsers.common import ParseError, records
from .common import card_for
from .cycles import remaining_clock

if TYPE_CHECKING:
    from .bounties import BountyRegion

logger = logging.getLogger(__name__)


def objective_lines(challenge: dict, ally: str) -> list[str]:
    text = challenge["description"].replace("|COUNT|", str(challenge["count"]))
    text = text.replace("|ALLY|", ally).replace("|OPEN_COLOR|", "").replace("|CLOSE_COLOR|", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and lines[0].endswith("赏金任务"):
        lines.pop(0)
    if any(re.search(r"\|[A-Z_]+\|", line) for line in lines):
        raise ParseError("赏金目标仍包含未解析的语言参数")
    return lines


def build_challenge_bounties(
    snapshot: Snapshot,
    now: datetime,
    index: int | None,
    *,
    region: str,
    config: "BountyRegion",
) -> Card:
    card = card_for(snapshot, config.title)
    card.bounty_mode = card.bounty_challenge_mode = True
    card.bounty_detail = index is not None
    card.bounty_region, card.bounty_currency = config.location, config.currency
    missions, _ = records(snapshot.data, "SyndicateMissions", SyndicateMission)
    active = [m for m in missions if m.tag == config.syndicate and m.activation <= now < m.expiry]
    if not active:
        card.status = DataStatus.EMPTY
        return card
    current = max(active, key=lambda m: m.activation)
    if current.seed is None:
        card.status = DataStatus.UNAVAILABLE
        card.notes.append("当前赏金轮换数据暂缺。")
        return card
    card.bounty_expiry = current.expiry
    card.bounty_remaining = remaining_clock(current.expiry, now)
    data = load_mapping("challenge_bounties.json")
    manifest = data["manifests"][region]
    agents = list(data["allies"].values()) if region == "hex" else None
    generated = generate_challenge_bounties(manifest, current.seed, agents)
    for number, (bounty, tier) in enumerate(
        zip(generated, manifest["ChallengeMissionDifficultyTiers"]), 1
    ):
        node = data["nodes"][bounty["node"]]
        challenge = data["challenges"][bounty["challenge"]]
        ally = ""
        if "ally" in bounty:
            ally_key = bounty["ally"].rsplit("/", 1)[-1].removesuffix("AllyAgent")
            ally = data["ally_names"][ally_key]
        faction = (
            ("Grineer", "Corpus")[current.seed & 1] if region == "zariman" else node["faction"]
        )
        modifier = tier["enemyLevelModifier"]
        card.bounty_items.append(
            BountyDisplay(
                index=number,
                name=challenge["name"],
                node=node["name"],
                mission=node["missionName"],
                faction=faction,
                objectives=objective_lines(challenge, ally),
                ally=ally,
                chemistry=tier.get("chemistryAmount", 0),
                kind="杀毒" if "InfestedLichBountyRewards" in tier["rewards"] else "常规",
                min_level=node["minEnemyLevel"] + modifier,
                max_level=node["maxEnemyLevel"] + modifier,
                standing=tier["xpAmount"],
                stages=1,
                mastery=None,
                rotation="—",
                reward_labels=["完成奖励"],
                reward_caption="完成赏金的单次奖励概率。",
            )
        )
    if index is not None:
        if not 1 <= index <= len(card.bounty_items):
            raise UserInputError(
                f"本期共有 {len(card.bounty_items)} 项赏金，例如：{config.title}1。"
            )
        selected = card.bounty_items[index - 1]
        key = manifest["ChallengeMissionDifficultyTiers"][index - 1]["rewards"]
        try:
            selected.rewards = merge_reward_pools(
                load_mapping("challenge_bounty_drops.json").get(key), [0]
            )
        except ParseError:
            logger.warning("赏金完成奖励暂不可用：%s", key, exc_info=True)
            selected.message = "完成奖励数据暂缺"
        card.bounty_items = [selected]
        card.title = f"{config.title} · {index}"
    return card
