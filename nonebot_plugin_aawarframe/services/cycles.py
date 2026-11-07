import logging
from datetime import datetime

from ..models.common import Section, Snapshot
from ..worldstate.parsers.common import ParseError
from ..worldstate.parsers.cycles import (cambion_cycle, cetus_cycle, duviri_cycle,
                                        earth_cycle, vallis_cycle)
from .cetus import remaining_time
from .common import card_for

logger = logging.getLogger(__name__)


def build_plains(snapshot: Snapshot, now: datetime):
    card = card_for(snapshot, "平原状态")
    section = Section(title="当前周期", columns=["区域", "当前状态", "距离切换", "下一状态", "切换时间 UTC"])
    card.sections = [section]
    card.notes = [f"状态计算时间：{now:%Y-%m-%d %H:%M:%S} UTC",
                  "夜灵平野与魔胎之境按官方赏金时间推算；其余按固定周期推算，游戏更新可能调整周期。",
                  "地球为普通任务昼夜，与夜灵平野独立。"]
    for name, parser in [("夜灵平野", cetus_cycle), ("福尔图娜（奥布山谷）", vallis_cycle),
                         ("魔胎之境", cambion_cycle), ("双衍王境", duviri_cycle), ("地球", earth_cycle)]:
        try:
            if parser in (cetus_cycle, cambion_cycle):
                cycle, warnings = parser(snapshot.data, now)
                card.notes.extend(note for note in warnings if note not in card.notes)
            else:
                cycle = parser(now)
            section.rows.append([cycle.location, cycle.state, remaining_time(cycle.expiry, now),
                                 cycle.next_state, cycle.expiry.strftime("%m-%d %H:%M:%S")])
        except (ParseError, ValueError, KeyError, TypeError):
            logger.exception("%s 周期解析失败", name)
            section.rows.append([name, "解析失败 / 无可用周期", "—", "—", "—"])
            card.notes.append(f"{name}周期不可用，其他区域不受影响。")
    return card
