from ..localization.resolver import load_mapping, translate
from ..models.common import Section, Snapshot
from ..models.worldstate import Conquest, ConquestMission
from ..worldstate.parsers.common import ParseError, records
from .common import card_for, finish


def build_archimedea(snapshot: Snapshot, kind: str):
    card = card_for(snapshot, "深层科研" if kind == "CT_LAB" else "时光科研")
    conquests, card.notes = records(snapshot.data, "Conquests", Conquest)
    target = next((c for c in conquests if c.type == kind), None)
    if target is None:
        return finish(card)
    prefix = "/Lotus/Language/Conquest/MissionVariant_" + (
        "LabConquest_" if kind == "CT_LAB" else "HexConquest_"
    )
    missions, warnings = records({"Missions": target.missions}, "Missions", ConquestMission)
    card.notes.extend(warnings)
    for i, mission in enumerate(missions, 1):
        difficulty = next((d for d in mission.difficulties if d.type == "CD_HARD"), None)
        difficulty = difficulty or next(
            (d for d in mission.difficulties if d.type == "CD_NORMAL"), None
        )
        if difficulty is None:
            card.notes.append(f"任务 {i} 缺少已知难度配置")
            continue
        keys = [prefix + difficulty.deviation] if difficulty.deviation else []
        keys += ["/Lotus/Language/Conquest/Condition_" + risk for risk in difficulty.risks]
        card.sections.append(
            Section(
                title=f"{i}. {translate(mission.mission_type)} · {translate(mission.faction)}",
                columns=["条件", "说明"],
                rows=[[translate(key), translate(key + "_Desc")] for key in keys],
                notes=[] if keys else ["无额外条件"],
            )
        )
    variable_map = load_mapping("variables.json")
    variable_keys = [
        "/Lotus/Language/Conquest/PersonalMod_" + variable_map.get(name, name)
        for name in target.variables
    ]
    card.sections.append(
        Section(
            title="个人变量",
            columns=["变量", "说明"],
            rows=[[translate(key), translate(key + "_Desc")] for key in variable_keys],
        )
    )
    if target.missions and not missions:
        raise ParseError("科研任务解析失败")
    return card
