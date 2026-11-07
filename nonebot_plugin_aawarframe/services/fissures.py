from datetime import datetime

from ..localization.resolver import node_info, translate
from ..models.common import Card, Section, Snapshot
from ..models.worldstate import Fissure, VoidStorm
from ..worldstate.parsers.common import records
from .common import card_for, finish

TIERS = {
    f"VoidT{i}": name for i, name in enumerate(["古纪", "前纪", "中纪", "后纪", "安魂", "全能"], 1)
}


def build_fissures(snapshot: Snapshot, now: datetime, *, hard: bool = False) -> Card:
    missions, warnings = records(snapshot.data, "ActiveMissions", Fissure)
    return _build_card(
        snapshot,
        now,
        "钢铁裂缝" if hard else "虚空裂缝",
        [mission for mission in missions if mission.hard == hard],
        warnings,
    )


def build_void_storms(snapshot: Snapshot, now: datetime) -> Card:
    missions, warnings = records(snapshot.data, "VoidStorms", VoidStorm)
    return _build_card(snapshot, now, "九重天虚空裂缝", missions, warnings)


def _build_card(
    snapshot: Snapshot,
    now: datetime,
    title: str,
    missions: list[Fissure] | list[VoidStorm],
    warnings: list[str],
) -> Card:
    card = card_for(snapshot, title)
    card.notes = warnings
    section = Section(
        title="当前任务", columns=["遗物", "节点 / 星球", "任务 / 派系", "结束时间 UTC"]
    )
    for mission in sorted(missions, key=lambda item: (item.modifier, item.expiry)):
        if not mission.activation <= now < mission.expiry:
            continue
        node = node_info(mission.node)
        section.rows.append(
            [
                TIERS.get(mission.modifier, mission.modifier),
                f"{node.get('name', mission.node)} / {node.get('systemName', '未知星球')}",
                f"{node.get('missionName', '未知任务')} / {translate(node.get('faction', '未知派系'))}",
                mission.expiry.strftime("%m-%d %H:%M"),
            ]
        )
    card.sections = [section]
    return finish(card)
