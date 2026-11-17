"""订阅规则：业务事件身份和提醒时间均使用 UTC。"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models.worldstate import CycleState

CETUS_PERIOD = timedelta(minutes=150)
CETUS_DAY = timedelta(minutes=100)
REMINDER_GRACE = timedelta(seconds=90)
CETUS_RULE = re.compile(r"^(?:地球平原|夜灵平野|希图斯)(?:\s+提前(\d{1,2})分钟)?$")


@dataclass(frozen=True)
class Occurrence:
    key: str
    due_at: datetime
    event_at: datetime


def parse_cetus_rule(arguments: str) -> int:
    """返回提前提醒的分钟数；不解析其他未实现的订阅类型。"""
    match = CETUS_RULE.fullmatch(arguments.strip())
    if not match:
        raise ValueError("用法：订阅 地球平原 [提前5分钟]")
    minutes = int(match.group(1)) if match.group(1) else 15
    if not 1 <= minutes <= 90:
        raise ValueError("提前时间应为 1–90 分钟。")
    return minutes


def next_cetus_occurrence(
    cycle: CycleState, now: datetime, created_at: datetime, lead_minutes: int
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
    due_at = night_at - timedelta(minutes=lead_minutes)
    lower_bound = max(created_at, now - REMINDER_GRACE)
    while due_at < lower_bound:
        night_at += CETUS_PERIOD
        due_at = night_at - timedelta(minutes=lead_minutes)
    return Occurrence(
        key="cetus-night:" + night_at.isoformat(),
        due_at=due_at,
        event_at=night_at,
    )
