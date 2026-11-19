# 作用：统一各地赏金查询，按任务类型生成概览、据点及奖励详情。
# 编写日期：2026-11-07
# 作者：Aameow

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from ..grq import get_grq
from ..localization.resolver import load_mapping
from ..models.bounties import BountyDisplay
from ..models.common import DataStatus, Section, Snapshot
from ..models.errors import UserInputError
from ..models.worldstate import SyndicateJob, SyndicateMission
from ..worldstate.parsers.bounties import merge_reward_pools, parse_rewards
from ..worldstate.parsers.common import ParseError, records
from ..worldstate.parsers.location_bounties import location_bounties
from .challenge_bounties import build_challenge_bounties
from .common import card_for
from .cycles import remaining_clock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BountyRegion:
    title: str
    syndicate: str
    location: str
    currency: str = "基础声望"
    challenge_based: bool = False


BOUNTY_REGIONS = {
    "earth": BountyRegion("地球赏金", "CetusSyndicate", "夜灵平野 · 希图斯"),
    "venus": BountyRegion("金星赏金", "SolarisSyndicate", "奥布山谷 · 福尔图纳"),
    "deimos": BountyRegion("火卫二赏金", "EntratiSyndicate", "魔胎之境 · 殁世幽都", "母亲石印"),
    "sanctum": BountyRegion(
        "圣所赏金", "EntratiLabSyndicate", "解剖圣所 · 英择谛实验室", challenge_based=True
    ),
    "zariman": BountyRegion(
        "扎里曼赏金", "ZarimanSyndicate", "扎里曼号 · 羽化之穹", "虚空刺翎", challenge_based=True
    ),
    "hex": BountyRegion("1999赏金", "HexSyndicate", "霍瓦尼亚 · 六人组", challenge_based=True),
}
BOUNTY_FEATURES = {
    "bounties": "earth",
    "venus_bounties": "venus",
    "deimos_bounties": "deimos",
    "sanctum_bounties": "sanctum",
    "zariman_bounties": "zariman",
    "hex_bounties": "hex",
}


def bounty_kind(job: SyndicateJob) -> str:
    if job.is_vault:
        return "隔离库"
    if job.endless:
        return "无尽"
    if "/Narmer/" in job.job_type:
        return "合一众"
    if job.min_level == job.max_level == 100:
        return "钢铁之路"
    return "常规"


def build_bounties(
    snapshot: Snapshot,
    now: datetime,
    index: int | None = None,
    *,
    region: str = "earth",
):
    config = BOUNTY_REGIONS[region]
    if config.challenge_based:
        return build_challenge_bounties(snapshot, now, index, region=region, config=config)
    card = card_for(snapshot, config.title)
    card.bounty_region = config.location
    card.bounty_currency = config.currency
    card.bounty_mode = True
    card.bounty_detail = index is not None
    missions, warnings = records(snapshot.data, "SyndicateMissions", SyndicateMission)
    active = [
        mission
        for mission in missions
        if mission.tag == config.syndicate and mission.activation <= now < mission.expiry
    ]
    if not active:
        card.status = DataStatus.EMPTY
        return card
    current = max(active, key=lambda mission: mission.activation)
    jobs, job_warnings = records({"Jobs": current.jobs}, "Jobs", SyndicateJob)
    if warnings or job_warnings:
        card.notes.append("部分任务暂时无法显示。")
    card.bounty_expiry = current.expiry
    card.bounty_remaining = remaining_clock(current.expiry, now)
    ordered = sorted(
        jobs,
        key=lambda job: (
            {"常规": 0, "无尽": 0, "钢铁之路": 1, "合一众": 2, "隔离库": 3}[bounty_kind(job)],
            job.min_level,
            job.max_level,
        ),
    )
    for number, job in enumerate(ordered, 1):
        name = job.job_type.rsplit("/", 1)[-1]
        description = get_grq().get("Desc", name + "Title")
        display_name = description.name() if description else name
        if job.is_vault:
            tier = {30: 1, 40: 2, 50: 3}.get(job.min_level)
            display_name = f"隔离库 · {tier} 级" if tier else "隔离库"
            if job.location_tag:
                display_name += "（" + job.location_tag.replace("Chamber", "区域 ") + "）"
        rotation = re.search(r"Table([ABC])Rewards$", job.rewards)
        view = BountyDisplay(
            index=number,
            name=display_name,
            kind=bounty_kind(job),
            min_level=job.min_level,
            max_level=job.max_level,
            stages=len(job.xp_amounts),
            standing=sum(job.xp_amounts) if job.xp_amounts else None,
            mastery=job.mastery_req,
            rotation=rotation.group(1) if rotation else "—",
        )
        card.bounty_items.append(view)
    if not card.bounty_items:
        card.status = DataStatus.EMPTY
        return card
    if index is None:
        if current.seed is not None:
            card.bounty_locations = location_bounties(current.seed, region)
        else:
            card.notes.append("据点赏金暂时无法获取。")
    if index is not None:
        if not 1 <= index <= len(card.bounty_items):
            raise UserInputError(
                f"本期共有 {len(card.bounty_items)} 项赏金，请输入对应编号，例如：{config.title}1。"
            )
        selected = card.bounty_items[index - 1]
        job = ordered[index - 1]
        try:
            drops = load_mapping("drops.json")
            pools = drops.get(job.rewards) or load_mapping("bounty_drops.json").get(job.rewards)
            if job.is_vault:
                # 隔离库仅在完成时掉落；四阶段表属于地下赏金，不能直接套用。
                key = job.rewards.replace("/Lotus/Types/Game/MissionDecks/", "/Supplementals/")
                completion = load_mapping("bounty_drops.json").get(key)
                if not completion:
                    raise ParseError("隔离库完成奖励暂缺")
                selected.rewards = merge_reward_pools(completion, [0])
                selected.reward_labels = ["完成奖励"]
                selected.reward_caption = "完成隔离库的单次奖励概率；不含额外奖励次数。"
            else:
                count = 3 if job.endless else 5
                selected.rewards = parse_rewards(pools, count)
                if job.endless:
                    selected.reward_labels = [f"阶段 {i}" for i in range(1, 4)]
                    selected.reward_caption = "本轮三阶段奖励概率参考；后续轮次可能不同。"
        except ParseError:
            logger.warning("赏金奖励暂不可用：%s", job.rewards, exc_info=True)
            selected.message = "阶段奖励数据暂缺"
        pool_resource = get_grq().get(
            "Misc", f"bounty.tasks.{region}:" + job.job_type.rsplit("/", 1)[-1]
        )
        pool = pool_resource.metadata["value"] if pool_resource else None
        if pool and bounty_kind(job) not in {"合一众", "隔离库"}:
            selected.task_pools = pool["stages"]
            if job.endless:
                selected.task_pool_title = "本轮三阶段可能任务池"
        else:
            selected.task_pool_note = "此类任务的阶段任务池尚未收录。"
        card.bounty_items = [selected]
        card.title = f"{config.title} · {selected.index}"
    return card


def build_bounty_summary(snapshot: Snapshot, now: datetime):
    """使用同一份世界状态，汇总常用的据点与高阶赏金。"""
    card = card_for(snapshot, "赏金速览")
    card.page_number = card.total_pages = 1
    earth = build_bounties(snapshot, now)
    card.sections.append(
        Section(
            title=f"地球 · 三个帐篷 · 剩余 {earth.bounty_remaining or '—'}",
            columns=["帐篷", "任务"],
            rows=[[location, "\n".join(jobs)] for location, jobs in earth.bounty_locations.items()],
            notes=[] if earth.bounty_locations else ["当前帐篷任务暂时无法获取。"],
        )
    )
    for region in ("sanctum", "zariman", "hex"):
        source = build_bounties(snapshot, now, region=region)
        selected = [
            job
            for job in source.bounty_items
            if job.index in {4, 5} or (region == "hex" and job.kind == "杀毒")
        ]
        rows = []
        for job in selected:
            label = f"{job.index}. {job.mission}"
            if job.kind == "杀毒":
                label += " (杀毒)"
            details = [f"{job.node} · {job.min_level}–{job.max_level} 级", *job.objectives]
            if job.ally:
                details.append(f"同行 {job.ally} · 好感度 +{job.chemistry}")
            rows.append([label, "\n".join(details)])
        card.sections.append(
            Section(
                title=f"{source.title} · 剩余 {source.bounty_remaining or '—'}",
                columns=["任务", "地点与目标"],
                rows=rows,
                notes=[] if rows else ["当前赏金暂时无法获取。"],
            )
        )
    return card
