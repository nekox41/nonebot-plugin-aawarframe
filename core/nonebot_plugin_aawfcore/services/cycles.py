# 作用：组装平原总览及各区域周期卡片。
# 编写日期：2026-11-07
# 作者：Aameow

import logging
from datetime import datetime, timedelta, timezone
from math import ceil

from ..models.common import Card, CycleDisplay, DataStatus, Section, Snapshot
from ..models.worldstate import CycleState
from ..worldstate.parsers.common import ParseError
from ..worldstate.parsers.cycles import (
    cambion_cycle,
    cetus_cycle,
    duviri_cycle,
    earth_cycle,
    vallis_cycle,
)
from .common import card_for

logger = logging.getLogger(__name__)
CHINA_TIME = timezone(timedelta(hours=8))
CYCLE_PARSERS = {
    "cetus": ("夜灵平野", cetus_cycle),
    "vallis": ("福尔图纳 · 奥布山谷", vallis_cycle),
    "cambion": ("魔胎之境", cambion_cycle),
    "duviri": ("双衍王境", duviri_cycle),
    "earth": ("地球", earth_cycle),
}
STATE_TONES = {
    "白天": "day",
    "黑夜": "night",
    "温暖": "warm",
    "寒冷": "cold",
    "Fass": "warm",
    "Vome": "night",
    "悲伤": "cold",
    "恐惧": "night",
    "喜悦": "day",
    "愤怒": "warm",
    "嫉妒": "green",
}


def remaining_time(expiry: datetime, now: datetime) -> str:
    seconds = max(0, ceil((expiry - now).total_seconds()))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (f"{hours} 小时 " if hours else "") + f"{minutes} 分 {seconds} 秒"


def remaining_clock(expiry: datetime, now: datetime) -> str:
    seconds = max(0, ceil((expiry - now).total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def parse_cycle(feature: str, snapshot: Snapshot, now: datetime) -> CycleState:
    _, parser = CYCLE_PARSERS[feature]
    if feature in {"cetus", "cambion"}:
        cycle, warnings = parser(snapshot.data, now)
        for warning in warnings:
            logger.warning("周期数据：%s", warning)
        return cycle
    return parser(now)


def cycle_display(feature: str, cycle: CycleState, now: datetime) -> CycleDisplay:
    return CycleDisplay(
        name=CYCLE_PARSERS[feature][0],
        state=cycle.state,
        next_state=cycle.next_state,
        remaining=remaining_time(cycle.expiry, now),
        remaining_short=remaining_clock(cycle.expiry, now),
        expiry=cycle.expiry,
        tone=STATE_TONES.get(cycle.state, "neutral"),
    )


def build_cycle(snapshot: Snapshot, now: datetime, feature: str) -> Card:
    name = CYCLE_PARSERS[feature][0]
    card = card_for(snapshot, name)
    try:
        cycle = parse_cycle(feature, snapshot, now)
        card.cycle_items = [cycle_display(feature, cycle, now)]
    except (ParseError, ValueError, KeyError, TypeError):
        logger.exception("%s 周期解析失败", name)
        card.status = DataStatus.PARSE_ERROR
        card.cycle_items = [CycleDisplay(name=name, state="暂时无法获取", available=False)]
        return card
    if feature == "cetus":
        next_night = (
            cycle.expiry if cycle.state == "白天" else cycle.expiry + timedelta(seconds=6000)
        )
        card.sections = [
            Section(
                title="接下来五次黑夜",
                columns=["次序", "开始时间（北京时间）"],
                rows=[
                    [
                        f"{i + 1:02}",
                        (next_night + timedelta(seconds=i * 9000))
                        .astimezone(CHINA_TIME)
                        .strftime("%m-%d %H:%M"),
                    ]
                    for i in range(5)
                ],
            )
        ]
    return card


def build_plains(snapshot: Snapshot, now: datetime) -> Card:
    card = card_for(snapshot, "平原总览")
    for feature, (name, _) in CYCLE_PARSERS.items():
        try:
            cycle = parse_cycle(feature, snapshot, now)
            card.cycle_items.append(cycle_display(feature, cycle, now))
        except (ParseError, ValueError, KeyError, TypeError):
            logger.exception("%s 周期解析失败", name)
            card.cycle_items.append(CycleDisplay(name=name, state="暂时无法获取", available=False))
    if not any(cycle.available for cycle in card.cycle_items):
        card.status = DataStatus.PARSE_ERROR
    return card
