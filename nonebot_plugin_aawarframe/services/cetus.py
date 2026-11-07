from datetime import datetime, timedelta
from math import ceil

from ..models.common import Section, Snapshot
from ..worldstate.parsers.cycles import cetus_cycle
from .common import card_for


def remaining_time(expiry: datetime, now: datetime) -> str:
    seconds = max(0, ceil((expiry - now).total_seconds()))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (f"{hours} 小时 " if hours else "") + f"{minutes} 分 {seconds} 秒"


def build_cetus(snapshot: Snapshot, now: datetime):
    card = card_for(snapshot, "夜灵：夜灵平野昼夜")
    cycle, card.notes = cetus_cycle(snapshot.data, now)
    next_night = cycle.expiry if cycle.state == "白天" else cycle.expiry + timedelta(seconds=6000)
    card.notes.extend([f"状态计算时间：{now:%Y-%m-%d %H:%M:%S} UTC", cycle.basis])
    card.sections = [
        Section(title="夜灵平野", columns=["当前状态", "距离切换", "下一状态", "切换时间 UTC"],
                rows=[[cycle.state, remaining_time(cycle.expiry, now), cycle.next_state,
                       cycle.expiry.strftime("%m-%d %H:%M:%S")]]),
        Section(title="接下来五次黑夜", columns=["次序", "开始时间 UTC"],
                rows=[[str(i + 1), (next_night + timedelta(seconds=i * 9000)).strftime("%m-%d %H:%M")]
                      for i in range(5)]),
    ]
    return card
