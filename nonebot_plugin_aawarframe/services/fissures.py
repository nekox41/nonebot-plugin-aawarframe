# 作用：筛选普通、钢铁与九重天裂缝，整理任务列表及剩余时间。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime

from ..localization.resolver import node_info, translate
from ..models.common import Card, DataStatus, FissureDisplay, Snapshot
from ..models.worldstate import Fissure, VoidStorm
from ..worldstate.parsers.common import records
from .common import card_for
from .cycles import remaining_clock, remaining_time

TIERS = {
    f"VoidT{i}": name for i, name in enumerate(["古纪", "前纪", "中纪", "后纪", "安魂", "全能"], 1)
}


def build_fissures(snapshot: Snapshot, now: datetime, *, hard: bool = False) -> Card:
    missions, warnings = records(snapshot.data, "ActiveMissions", Fissure)
    return _build_card(
        snapshot,
        now,
        "钢铁裂缝" if hard else "裂缝",
        [mission for mission in missions if mission.hard == hard],
        warnings,
        mode="steel" if hard else "normal",
    )


def build_void_storms(snapshot: Snapshot, now: datetime) -> Card:
    missions, warnings = records(snapshot.data, "VoidStorms", VoidStorm)
    return _build_card(snapshot, now, "九重天裂缝", missions, warnings, mode="railjack")


def _build_card(
    snapshot: Snapshot,
    now: datetime,
    title: str,
    missions: list[Fissure] | list[VoidStorm],
    warnings: list[str],
    *,
    mode: str,
) -> Card:
    card = card_for(snapshot, title)
    card.fissure_mode = mode
    # 解析细节留在日志中，卡片只提示用户需要知道的信息。
    if warnings:
        card.notes = ["部分任务暂时无法显示。"]
    tier_order = {key: index for index, key in enumerate(TIERS)}
    for mission in sorted(
        missions,
        key=lambda item: (
            tier_order.get(item.modifier, len(TIERS)),
            item.modifier,
            item.expiry,
            item.node,
        ),
    ):
        if not mission.activation <= now < mission.expiry:
            continue
        node = node_info(mission.node)
        card.fissure_items.append(
            FissureDisplay(
                tier=TIERS.get(mission.modifier, mission.modifier),
                tier_key=mission.modifier if mission.modifier in TIERS else "unknown",
                node=str(node.get("name", mission.node)),
                planet=str(node.get("systemName", "未知星球")),
                mission=str(node.get("missionName", "未知任务")),
                faction=translate(node.get("faction", "未知派系")),
                remaining=remaining_time(mission.expiry, now),
                remaining_short=remaining_clock(mission.expiry, now),
                expiry=mission.expiry,
                urgent=(mission.expiry - now).total_seconds() <= 300,
            )
        )
    card.item_total = len(card.fissure_items)
    if not card.fissure_items:
        card.status = DataStatus.EMPTY
    return card
