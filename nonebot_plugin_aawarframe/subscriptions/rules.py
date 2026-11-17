"""订阅参数规范化；业务事件身份与提醒时间统一使用 UTC。"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models.worldstate import CycleState

CETUS_PERIOD = timedelta(minutes=150)
CETUS_DAY = timedelta(minutes=100)
REMINDER_GRACE = timedelta(seconds=90)
CETUS_LEAD_MINUTES = 15
CETUS_RULE = re.compile(r"^(?:夜灵|地球平原)$")
TIERS = {"古纪": "VoidT1", "前纪": "VoidT2", "中纪": "VoidT3",
         "后纪": "VoidT4", "安魂": "VoidT5", "全能": "VoidT6"}
REGIONS = {"地球": "CetusSyndicate", "金星": "SolarisSyndicate",
           "火卫二": "EntratiSyndicate", "圣所": "EntratiLabSyndicate",
           "扎里曼": "ZarimanSyndicate", "1999": "HexSyndicate"}
BOUNTY_KINDS = {"常规", "钢铁之路", "合一众", "无尽", "隔离库"}
MARKET_PATTERN = re.compile(r"^wm\s+(.+?)\s+卖价(?:<=|≤)(\d{1,6})$", re.I)


@dataclass(frozen=True)
class Occurrence:
    key: str
    due_at: datetime
    event_at: datetime


@dataclass(frozen=True)
class RuleSpec:
    kind: str
    rule: dict


def parse_cetus_rule(arguments: str) -> None:
    if not CETUS_RULE.fullmatch(arguments.strip()):
        raise ValueError("用法：订阅 夜灵 或 订阅 地球平原（固定提前 15 分钟）")


def parse_rule(arguments: str) -> RuleSpec:
    value = " ".join(arguments.split())
    if CETUS_RULE.fullmatch(value):
        return RuleSpec("cetus_night", {"lead_minutes": 15})
    parts = value.split()
    if parts and parts[0] == "裂缝":
        if len(parts) < 2 or len(parts) > 5:
            raise ValueError("用法：订阅 裂缝 古纪 生存 / 订阅 裂缝 虚空 生存")
        filters = parts[1:]
        hard = "钢铁" in filters
        if hard:
            filters.remove("钢铁")
        tiers = [t for t in filters if t in TIERS]
        if len(tiers) > 1:
            raise ValueError("每条裂缝订阅只能指定一个纪元。")
        tier = tiers[0] if tiers else ""
        if tier:
            filters.remove(tier)
        planet = "虚空" if "虚空" in filters else ""
        if planet:
            filters.remove(planet)
        if len(filters) > 1 or (filters and len(filters[0]) > 20):
            raise ValueError("裂缝筛选条件过多，请仅输入纪元、星球和任务类型。")
        if not (tier or planet or filters or hard):
            raise ValueError("请至少填写一个裂缝筛选条件。")
        return RuleSpec("fissure", {"tier": tier, "planet": planet,
                                    "mission": filters[0] if filters else "",
                                    "hard": hard})
    if parts and parts[0] == "仲裁":
        if len(parts) != 2 or not 1 <= len(parts[1]) <= 24:
            raise ValueError("用法：订阅 仲裁 生存（固定提前 15 分钟）")
        return RuleSpec("arbitration", {"mission": parts[1]})
    if parts and parts[0] == "赏金":
        if len(parts) not in {2, 3} or parts[1] not in REGIONS or (
            len(parts) == 3 and parts[2] not in BOUNTY_KINDS
        ):
            raise ValueError("用法：订阅 赏金 地球 [常规/钢铁之路/合一众/无尽/隔离库]")
        return RuleSpec("bounty", {"region": parts[1],
                                   "type": parts[2] if len(parts) == 3 else ""})
    market = MARKET_PATTERN.fullmatch(value)
    if market:
        return RuleSpec("market", {"name": market.group(1), "price": int(market.group(2))})
    raise ValueError(
        "用法：订阅 夜灵 / 地球平原 / 裂缝 古纪 生存 / 仲裁 生存 / "
        "赏金 地球 / wm 伯斯顿 卖价<=50"
    )


def describe(kind: str, rule: dict) -> str:
    if kind == "cetus_night":
        return "夜灵平野 · 黑夜前15分钟"
    if kind == "fissure":
        return "裂缝 · " + " ".join(filter(None, (
            "钢铁" if rule.get("hard") else "", rule.get("tier", ""),
            rule.get("planet", ""), rule.get("mission", ""),
        )))
    if kind == "arbitration":
        return "仲裁 · " + rule.get("mission", "") + " · 提前15分钟"
    if kind == "bounty":
        return "赏金 · " + rule.get("region", "") + (
            " · " + rule["type"] if rule.get("type") else ""
        )
    if kind == "market":
        return "Market · " + rule.get("name", rule.get("slug", "")) + (
            " · 卖价≤" + str(rule.get("price", "?")) + "白金"
        )
    return kind


def next_cetus_occurrence(cycle: CycleState, now: datetime, created_at: datetime) -> Occurrence:
    """本轮已错过提前时刻则等待下一轮，不追发订阅前发生的事件。"""
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
    return Occurrence(key="cetus-night:" + night_at.isoformat(),
                      due_at=due_at, event_at=night_at)
