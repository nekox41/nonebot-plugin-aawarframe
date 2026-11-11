# 作用：按已核对的八周周期展示钢铁精华本周与下周兑换物品。
# 编写日期：2026-11-11
# 作者：Aameow

from datetime import datetime

from ..localization.resolver import load_mapping
from ..models.common import Section, Snapshot
from .weekly import WEEK, week_bounds, weekly_card


def build_steel_path(snapshot: Snapshot, now: datetime):
    card = weekly_card(snapshot, "钢铁精华 · 每周兑换", now)
    data = load_mapping("weekly_rotations.json")
    start, _ = week_bounds(now)
    epoch = datetime.fromisoformat(data["steel_epoch"])
    index = (start - epoch) // WEEK
    for offset, title in ((0, "本周"), (1, "下周")):
        reward = data["steel"][(index + offset) % len(data["steel"])]
        card.sections.append(
            Section(
                title=title,
                columns=["兑换物品", "钢铁精华"],
                rows=[[reward["name"], str(reward["cost"])]],
            )
        )
    return card
