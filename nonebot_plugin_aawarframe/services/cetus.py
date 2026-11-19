# 作用：保留夜灵查询的统一业务入口。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime

from ..models.common import Card, Snapshot
from .cycles import build_cycle, remaining_time  # noqa: F401


def build_cetus(snapshot: Snapshot, now: datetime) -> Card:
    return build_cycle(snapshot, now, "cetus")
