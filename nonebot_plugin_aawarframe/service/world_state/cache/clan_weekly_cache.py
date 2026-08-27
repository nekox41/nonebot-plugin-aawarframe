import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from ....integrations.world_state import WeeklyVaultBonus, translate_batch


class ClanWeeklyCache:
    """
    氏族每周奖励缓存
    游戏刷新时间：每周一 08:00 (UTC+8)
    缓存策略：每次请求时检查是否已过刷新时间，如果过了则失效缓存
    """

    def __init__(self):
        self._data: Optional[List[WeeklyVaultBonus]] = None
        self._cached_time: datetime = None

    def _is_expired(self) -> bool:
        """
        检查缓存是否过期
        如果当前时间 >= 下一个刷新时间，说明缓存已过期
        """
        if self._data is None:
            return True

        now = datetime.now(timezone(timedelta(hours=8)))

        return (now - self._cached_time).days > 7

    def get(self) -> Optional[List[WeeklyVaultBonus]]:
        """获取缓存数据"""
        if self._is_expired():
            return None
        return self._data

    async def set(self, data: List[WeeklyVaultBonus]):
        """设置缓存，同时批量翻译"""
        # 收集所有需要翻译的标识
        self._data = data
        # 设置缓存时间
        now = datetime.now(timezone(timedelta(hours=8)))
        # 计算本周一的 08:00
        days_since_monday = now.weekday()  # 周一=0, 周日=6
        this_monday = now - timedelta(days=days_since_monday)
        this_monday_8am = this_monday.replace(hour=8, minute=0, second=0, microsecond=0)
        self._cached_time = this_monday_8am

        self._cached_time = now

    def invalidate(self):
        """手动失效缓存"""
        self._data = None
        self._cached_time = None


# 全局单例
cache = ClanWeeklyCache()
