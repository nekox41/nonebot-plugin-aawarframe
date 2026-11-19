# 作用：整理当期科研任务、普通与精英风险、个人变量及轮换时间。
# 编写日期：2026-11-11
# 作者：Aameow

import re
from datetime import datetime, timezone

from ..localization.resolver import load_mapping, normalize, translate
from ..models.common import DataStatus, Section, Snapshot, utcnow
from ..models.worldstate import Conquest, ConquestMission
from ..worldstate.parsers.common import ParseError, records
from .common import card_for
from .cycles import remaining_clock

PREFIX = "/Lotus/Language/Conquest/"


def modifier_row(category: str, key: str, identifier: str) -> list[str]:
    name, description = translate(key), translate(key + "_Desc")
    # 语言字典中的伤害图标为游戏标记，不是 HTML，也不应直接显示给用户。
    description = re.sub(r"<DT_[A-Z_]+>|\|(?:OPEN|CLOSE)_COLOR\|", "", description)
    if description == key + "_Desc":
        description = "说明暂缺"
    elif re.search(r"\|[^|]+\|", description):
        description = "具体数值以游戏内说明为准。"
    return [category, identifier if name == key else name, description.strip()]


def mission_rows(mission: ConquestMission, prefix: str) -> list[list[str]]:
    normal = next((d for d in mission.difficulties if d.type == "CD_NORMAL"), None)
    elite = next((d for d in mission.difficulties if d.type == "CD_HARD"), None)
    if normal is None and elite is None:
        raise ParseError("科研任务缺少普通与精英难度配置")
    rows = []
    if normal and normal.deviation:
        category = "偏差" if elite and elite.deviation == normal.deviation else "普通偏差"
        rows.append(modifier_row(category, prefix + normal.deviation, normal.deviation))
    if elite and elite.deviation and (normal is None or elite.deviation != normal.deviation):
        rows.append(modifier_row("精英偏差", prefix + elite.deviation, elite.deviation))
    if normal:
        for risk in dict.fromkeys(normal.risks):
            shared = elite is not None and risk in elite.risks
            rows.append(
                modifier_row("风险" if shared else "普通风险", PREFIX + "Condition_" + risk, risk)
            )
    if elite:
        for risk in dict.fromkeys(elite.risks):
            if normal is None or risk not in normal.risks:
                rows.append(modifier_row("精英风险", PREFIX + "Condition_" + risk, risk))
    return rows


def build_archimedea(snapshot: Snapshot, kind: str, now: datetime | None = None):
    if kind not in {"CT_LAB", "CT_HEX"}:
        raise ValueError(f"未知科研类型：{kind}")
    now = now or utcnow()
    card = card_for(snapshot, "深层科研" if kind == "CT_LAB" else "时光科研")
    card.archimedea_mode = True
    conquests, warnings = records(snapshot.data, "Conquests", Conquest)
    active = [
        c
        for c in conquests
        if c.type == kind
        and (c.activation is None or c.activation <= now)
        and (c.expiry is None or now < c.expiry)
    ]
    if warnings:
        card.notes.append("部分科研数据暂时无法显示。")
    if not active:
        card.status = DataStatus.EMPTY
        card.notes.append("当前没有可用的科研轮换，请稍后再试。")
        return card
    target = max(active, key=lambda c: c.activation or datetime.min.replace(tzinfo=timezone.utc))
    card.archimedea_activation = target.activation
    card.archimedea_expiry = target.expiry
    if target.expiry:
        card.archimedea_remaining = remaining_clock(target.expiry, now)
    prefix = PREFIX + "MissionVariant_" + ("LabConquest_" if kind == "CT_LAB" else "HexConquest_")
    valid_missions = 0
    # 按原始下标保留任务顺序，单条损坏不会令后续任务被误标为前一场。
    for number, raw in enumerate(target.missions, 1):
        try:
            mission = ConquestMission.model_validate(raw)
        except ValueError:
            card.sections.append(Section(title=f"任务 {number}", notes=["此任务数据暂缺。"]))
            continue
        valid_missions += 1
        try:
            rows = mission_rows(mission, prefix)
        except ParseError:
            rows = []
            notes = ["此任务难度配置暂缺。"]
        else:
            notes = [] if rows else ["无额外条件。"]
        card.sections.append(
            Section(
                title=f"{number}. {translate(mission.mission_type)} · {translate(mission.faction)}",
                columns=["类型", "条件", "说明"],
                rows=rows,
                notes=notes,
            )
        )
    if not valid_missions:
        raise ParseError("科研任务解析失败或为空")
    if valid_missions != len(target.missions):
        card.notes.append("部分科研任务暂时无法显示。")
    aliases = {normalize(key): value for key, value in load_mapping("variables.json").items()}
    variables = [aliases.get(normalize(name), name) for name in target.variables]
    card.sections.append(
        Section(
            title="个人变量",
            columns=["类型", "变量", "说明"],
            rows=[modifier_row("个人", PREFIX + "PersonalMod_" + name, name) for name in variables],
            notes=[] if variables else ["本期无个人变量。"],
        )
    )
    return card
