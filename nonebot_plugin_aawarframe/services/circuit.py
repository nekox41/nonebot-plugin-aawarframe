# 作用：展示回廊本周与下周奖励，并按周列出灵化武器轮换。
# 编写日期：2026-11-11
# 作者：Aameow

from datetime import datetime

from ..localization.resolver import load_mapping, normalize
from ..models.common import DataStatus, Section, Snapshot
from ..models.worldstate import CircuitWeek
from ..worldstate.parsers.common import records
from .weekly import active_rotation, weekly_card


def rotation_index(choices: list[str], rotation: list[list[str]]) -> int | None:
    # 完整匹配本周官方选项，避免轮换更新后依旧预测错误的下周。
    selected = {normalize(value.replace("&", "and")) for value in choices}
    return next(
        (
            index
            for index, row in enumerate(rotation)
            if selected == {normalize(value.replace("&", "and")) for value in row}
        ),
        None,
    )


def weapon_name(name: str) -> str:
    names = load_mapping("riven_weapons.json")
    if name in names:
        return names[name]
    aliases = {normalize(key.replace("&", "and")): value for key, value in names.items()}
    return aliases.get(normalize(name.replace("&", "and")), name)


def circuit_week(snapshot: Snapshot, now: datetime):
    weeks, warnings = records(snapshot.data, "EndlessXpSchedule", CircuitWeek)
    return active_rotation(weeks, now), warnings


def build_circuit(snapshot: Snapshot, now: datetime, *, all_incarnons: bool = False):
    card = weekly_card(
        snapshot, "灵化武器 · 周轮换" if all_incarnons else "无尽回廊 · 每周奖励", now
    )
    current, warnings = circuit_week(snapshot, now)
    if current is None:
        card.status = DataStatus.EMPTY
        card.notes.append("本期回廊选项尚未公布。")
        return card
    card.rotation_expiry = current.expiry
    if warnings:
        card.notes.append("部分回廊数据暂时无法显示。")
    rotations = load_mapping("weekly_rotations.json")
    categories = {category.category: category.choices for category in current.categories}
    if all_incarnons:
        rotation = rotations["hard"]
        index = rotation_index(categories.get("EXC_HARD", []), rotation)
        section = Section(
            title="每周灵化武器",
            columns=["轮换周", "武器一", "武器二", "武器三", "武器四", "武器五"],
        )
        for number, weapons in enumerate(rotation):
            section.rows.append(
                [
                    f"第 {number + 1} 周" + (" · 本周" if number == index else ""),
                    *map(weapon_name, weapons),
                ]
            )
        section.highlighted_rows = [] if index is None else [index]
        card.sections = [section]
        if index is None:
            card.notes.append("本周官方选项与已知轮换表不一致，暂不标记当前周。")
        return card
    for category, key, title in [
        ("EXC_NORMAL", "normal", "普通回廊 · 战甲三选一"),
        ("EXC_HARD", "hard", "钢铁回廊 · 灵化五选二"),
    ]:
        choices = categories.get(category, [])
        rotation = rotations[key]
        index = rotation_index(choices, rotation)
        display = weapon_name if key == "hard" else str
        section = Section(
            title=title,
            columns=["周期", "可选奖励"],
            rows=[["本周", " / ".join(map(display, choices)) if choices else "本周选项暂缺"]],
        )
        upcoming = rotation[(index + 1) % len(rotation)] if index is not None else []
        section.rows.append(
            ["下周", " / ".join(map(display, upcoming)) if upcoming else "下期轮换暂时无法确认"]
        )
        card.sections.append(section)
    return card
