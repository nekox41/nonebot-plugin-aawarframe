# Desc: 提供周轮换时间、中文奖励名称和紧凑卡片的共享工具。
# Date: 2026-11-14
# Author: Aameow

import re
from datetime import datetime, timedelta, timezone

from ..grq import get_grq
from ..localization.resolver import load_mapping, translate
from ..models.common import Card, Snapshot
from .common import card_for

WEEK = timedelta(days=7)
ITEM_NAMES = {
    "mummyquestkeyblueprint": "《Inaros 之沙》任务蓝图",
    "glyphfactionorokin": "奥罗金浮印",
    "cny2023rabbitglyph": "癸卯浮印",
    "glyphfactionmurmur": "低语者浮印",
}


def week_bounds(now: datetime) -> tuple[datetime, datetime]:
    current = now.astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=current.weekday()
    )
    return start, start + WEEK


def weekly_card(snapshot: Snapshot, title: str, now: datetime) -> Card:
    card = card_for(snapshot, title)
    card.weekly_mode = True
    card.rotation_expiry = week_bounds(now)[1]
    return card


def item_name(path: str) -> str:
    name = ITEM_NAMES.get(path.rsplit("/", 1)[-1].casefold())
    if name:
        return name
    for ref in (path, path.replace("/StoreItems/", "/")):
        item = get_grq().get("Items", ref, "game.ref")
        if item and item.names.get("zh-hans"):
            return re.sub(r"<[^>]+>", "", item.names["zh-hans"])
    key = path.lower().replace("/lotus/storeitems/", "/lotus/")
    value = load_mapping("weekly_names.json").get(key)
    if value:
        return value
    translated = translate(path)
    return re.sub(r"<[^>]+>", "", translated if translated != path else path.rsplit("/", 1)[-1])


def active_rotation(rotations: list, now: datetime):
    active = [rotation for rotation in rotations if rotation.activation <= now < rotation.expiry]
    return max(active, key=lambda rotation: rotation.activation) if active else None
