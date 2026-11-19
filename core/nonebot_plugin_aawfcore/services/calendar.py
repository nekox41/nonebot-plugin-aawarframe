# 作用：按游戏内月份展示 1999 当期日历的任务与可选奖励。
# 编写日期：2026-11-11
# 作者：Aameow

from datetime import datetime, timedelta

from ..localization.resolver import load_mapping
from ..models.common import DataStatus, Section, Snapshot
from ..models.worldstate import CalendarSeason
from ..worldstate.parsers.common import records
from .common import finish
from .weekly import active_rotation, item_name, weekly_card

SEASONS = {"CST_WINTER": "冬季", "CST_SPRING": "春季", "CST_SUMMER": "夏季", "CST_FALL": "秋季"}


def build_calendar(snapshot: Snapshot, now: datetime):
    card = weekly_card(snapshot, "1999 每周日历", now)
    seasons, warnings = records(snapshot.data, "KnownCalendarSeasons", CalendarSeason)
    current = active_rotation(seasons, now)
    if current is None:
        card.status = DataStatus.EMPTY
        card.notes.append("当前日历尚未公布。")
        return card
    card.title += " · " + SEASONS.get(current.season, current.season)
    card.rotation_expiry = current.expiry
    if warnings:
        card.notes.append("部分日历数据暂时无法显示。")
    tasks = load_mapping("calendar_tasks.json")
    months = {}
    for day in sorted(current.days, key=lambda d: d.day):
        date = datetime(1999, 1, 1) + timedelta(days=day.day - 1)
        section = months.setdefault(
            date.month,
            Section(title=f"{date.month} 月", columns=["日期", "类型", "任务 / 可选奖励"]),
        )
        for event in day.events:
            if event.type == "CET_CHALLENGE" and event.challenge:
                info = tasks.get(event.challenge.lower())
                description = (
                    info["description"]
                    if info
                    else "任务说明暂缺：" + event.challenge.rsplit("/", 1)[-1]
                )
                section.rows.append([f"{date.month:02}-{date.day:02}", "任务", description])
        rewards = [
            item_name(event.reward)
            for event in day.events
            if event.type == "CET_REWARD" and event.reward
        ]
        if rewards:
            section.rows.append(
                [
                    f"{date.month:02}-{date.day:02}",
                    "奖励 · 二选一" if len(rewards) == 2 else "奖励",
                    "\n".join(rewards),
                ]
            )
    card.sections = [section for section in months.values() if section.rows]
    return finish(card)
