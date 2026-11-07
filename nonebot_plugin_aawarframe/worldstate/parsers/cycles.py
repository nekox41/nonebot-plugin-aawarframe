"""Local cycle calculations; timing references: WFCD/warframe-worldstate-parser.

No parsed community API is queried. Fixed schedules can change after game updates.
"""
from datetime import datetime, timedelta, timezone

from ...models.worldstate import CycleState, SyndicateMission
from .common import ParseError, records

VALLIS_ANCHOR = datetime(2026, 2, 4, 19, 46, 48, tzinfo=timezone.utc)
DUVIRI_STATES = ("悲伤", "恐惧", "喜悦", "愤怒", "嫉妒")


def cetus_cycle(raw: dict, now: datetime) -> tuple[CycleState, list[str]]:
    missions, warnings = records(raw, "SyndicateMissions", SyndicateMission)
    active = [mission for mission in missions
              if mission.tag == "CetusSyndicate" and mission.activation <= now < mission.expiry]
    if not active:
        raise ParseError("没有当前有效的希图斯赏金周期，无法推算昼夜。")
    mission = max(active, key=lambda item: item.activation)
    end = mission.expiry.replace(second=0, microsecond=0)
    remaining = (end - now).total_seconds()
    if not 0 < remaining <= 9000:
        raise ParseError("希图斯赏金结束时间超出有效周期，无法推算昼夜。")
    day = remaining > 3000
    return CycleState(location="夜灵平野", state="白天" if day else "黑夜",
                      next_state="黑夜" if day else "白天",
                      expiry=end - timedelta(seconds=3000) if day else end,
                      basis="官方希图斯赏金结束时间推算"), warnings


def vallis_cycle(now: datetime) -> CycleState:
    elapsed = (now - VALLIS_ANCHOR).total_seconds() % 1600
    warm = elapsed < 400
    return CycleState(location="福尔图娜（奥布山谷）", state="温暖" if warm else "寒冷",
                      next_state="寒冷" if warm else "温暖",
                      expiry=now + timedelta(seconds=(400 if warm else 1600) - elapsed),
                      basis="固定周期推算：温暖 6 分 40 秒 / 寒冷 20 分钟")


def earth_cycle(now: datetime) -> CycleState:
    elapsed = now.timestamp() % 28800
    day = elapsed < 14400
    return CycleState(location="地球", state="白天" if day else "黑夜",
                      next_state="黑夜" if day else "白天",
                      expiry=now + timedelta(seconds=(14400 if day else 28800) - elapsed),
                      basis="固定 UTC 周期推算：昼夜各 4 小时")


def duviri_cycle(now: datetime) -> CycleState:
    elapsed = (now.timestamp() - 52) % 36000
    index = int(elapsed // 7200)
    return CycleState(location="双衍王境", state=DUVIRI_STATES[index],
                      next_state=DUVIRI_STATES[(index + 1) % len(DUVIRI_STATES)],
                      expiry=now + timedelta(seconds=7200 - elapsed % 7200),
                      basis="固定周期推算：每个情绪 2 小时")


def cambion_cycle(raw: dict, now: datetime) -> tuple[CycleState, list[str]]:
    cetus, warnings = cetus_cycle(raw, now)
    day = cetus.state == "白天"
    return CycleState(location="魔胎之境", state="Fass" if day else "Vome",
                      next_state="Vome" if day else "Fass",
                      expiry=cetus.expiry, basis="官方希图斯赏金周期推算：Fass 100 分钟 / Vome 50 分钟"), warnings
