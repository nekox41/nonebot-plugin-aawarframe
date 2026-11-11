# 作用：解析午夜电波当期每日、每周与精英每周任务并生成展示卡片。
# 编写日期：2026-11-11
# 作者：Aameow

import re
from datetime import datetime, timezone

from ..localization.resolver import load_mapping
from ..models.common import Card, DataStatus, Section, Snapshot
from ..models.worldstate import NightwaveChallenge, NightwaveSeason
from ..worldstate.parsers.common import ParseError, records
from .common import card_for

GROUPS = (("daily", "每日任务"), ("weekly", "每周任务"), ("elite", "精英每周任务"))


def challenge_group(challenge: NightwaveChallenge) -> str:
    path = challenge.challenge.lower()
    if challenge.daily or "/daily/" in path:
        return "daily"
    return "elite" if "/weeklyhard/" in path else "weekly"


def remaining_time(expiry: datetime, now: datetime) -> str:
    minutes = max(1, int((expiry - now).total_seconds() + 59) // 60)
    days, hours = divmod(minutes // 60, 24)
    if days:
        return f"{days}天{hours}小时"
    if hours:
        return f"{hours}小时{minutes % 60}分"
    return f"{minutes}分"


def build_nightwave(snapshot: Snapshot, now: datetime) -> Card:
    card = card_for(snapshot, "午夜电波")
    card.nightwave_mode = True
    if "SeasonInfo" not in snapshot.data:
        raise ParseError("SeasonInfo 缺失")
    raw = snapshot.data["SeasonInfo"]
    if raw is None or raw == {}:
        card.status = DataStatus.EMPTY
        card.notes.append("当前没有进行中的午夜电波任务。")
        return card
    season = NightwaveSeason.model_validate(raw)
    if (season.activation is not None and now < season.activation) or (
        season.expiry is not None and now >= season.expiry
    ):
        card.status = DataStatus.EMPTY
        card.notes.append("当前没有进行中的午夜电波任务。")
        return card
    challenges, warnings = records(
        {"Challenges": season.challenges}, "Challenges", NightwaveChallenge
    )
    if warnings:
        card.notes.append("部分任务数据暂时无法显示。")
    active = [
        challenge for challenge in challenges if challenge.activation <= now < challenge.expiry
    ]
    translations = load_mapping("nightwave_zh.json")
    unknown = False
    today = now.astimezone(timezone.utc).date()
    for group, title in GROUPS:
        # 每日新任务置顶，同期周任务保留官方顺序。
        tasks = sorted(
            (item for item in active if challenge_group(item) == group),
            key=lambda item: (-item.activation.timestamp(), item.expiry),
        )
        rows = []
        seen = set()
        for task in tasks:
            key = (task.challenge.lower(), task.activation, task.expiry)
            if key in seen:
                continue
            seen.add(key)
            info = translations.get(task.challenge.lower())
            if info is None:
                unknown = True
                name, description = task.challenge.rsplit("/", 1)[-1], "任务说明暂缺"
                reputation = "—"
            else:
                name = info["name"]
                description = info["description"].replace("|COUNT|", str(info["required"]))
                description = re.sub(r"<DT_[A-Z_]+>", "", description)
                reputation = f"{info['standing']:,}"
            tag = ""
            if group == "daily" and task.activation.astimezone(timezone.utc).date() == today:
                tag = "今日新增"
            elif "/seasonweeklypermanent" in task.challenge.lower():
                tag = "常驻"
            rows.append([name, description, reputation, remaining_time(task.expiry, now), tag])
        card.sections.append(
            Section(
                title=title,
                columns=["任务", "目标", "声望", "剩余", "标记"],
                rows=rows,
                notes=[] if rows else ["当前暂无此类任务。"],
            )
        )
    if unknown:
        card.notes.append("部分新任务的中文说明暂缺。")
    if not active:
        card.status = DataStatus.EMPTY
    return card
