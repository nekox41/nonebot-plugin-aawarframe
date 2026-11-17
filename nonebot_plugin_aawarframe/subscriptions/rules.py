"""订阅规则：业务事件身份和提醒时间均使用 UTC。"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models.worldstate import CycleState

CETUS_PERIOD = timedelta(minutes=150)
CETUS_DAY = timedelta(minutes=100)
REMINDER_GRACE = timedelta(seconds=90)
CETUS_LEAD_MINUTES = 15
CETUS_RULE = re.compile(r"^(?:夜灵|地球平原)$")


@dataclass(frozen=True)
class Occurrence:
    key: str
    due_at: datetime
    event_at: datetime


def parse_cetus_rule(arguments: str) -> None:
    """只允许两个明确的订阅名称，提醒固定提前 15 分钟。"""
    if not CETUS_RULE.fullmatch(arguments.strip()):
        raise ValueError("用法：订阅 夜灵 或 订阅 地球平原（固定提前 15 分钟）")


def next_cetus_occurrence(
    cycle: CycleState, now: datetime, created_at: datetime
) -> Occurrence:
    """当前提醒时间已过去时，从下一次黑夜开始提醒。

    上游夜灵平野周期为 100 分钟白天 + 50 分钟黑夜。
    一次轮换对应一个稳定事件键，避免重启/重复轮询重复发信。
    """
    if cycle.state == "白天":
        night_at = cycle.expiry
    elif cycle.state == "黑夜":
        night_at = cycle.expiry + CETUS_DAY
    else:
        raise ValueError("无法识别夜灵平野昼夜状态")
    due_at = night_at - timedelta(minutes=CETUS_LEAD_MINUTES)
    lower_bound = max(created_at, now - REMINDER_GRACE)
    while due_at < lower_bound:
        night_at += CETUS_PERIOD
        due_at = night_at - timedelta(minutes=CETUS_LEAD_MINUTES)
    return Occurrence(
        key="cetus-night:" + night_at.isoformat(),
        due_at=due_at,
        event_at=night_at,
    )
