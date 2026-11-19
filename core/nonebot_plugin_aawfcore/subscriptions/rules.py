"""订阅命令规范化；业务发生时间和提醒时间均为 UTC。"""

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
FISSURE_MODES = {"裂缝": "normal", "钢铁裂缝": "steel", "九重天": "railjack"}
PLANETS = {
    "水星", "金星", "地球", "火星", "火卫一", "火卫二", "谷神星", "木星",
    "欧罗巴", "土星", "天王星", "海王星", "冥王星", "阋神星", "塞德娜",
    "虚空", "月球", "赤毒要塞", "扎里曼", "双衍王境",
}
MISSIONS = {
    "歼灭", "捕获", "生存", "防御", "移动防御", "拦截", "挖掘", "间谍",
    "破坏", "救援", "劫持", "清巢", "中断", "武装", "叛逃", "刺杀",
    "竞技场", "追击", "无限回廊", "虚空洪流", "虚空覆涌", "虚空决战",
    "资源回收", "炼金", "转换", "殲滅",
}
USER_ID = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
RIVEN_PATTERN = re.compile(r"^wmr\s+(.+?)\s+(\d{1,7})$", re.I)


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
    if parts and parts[0] in FISSURE_MODES:
        mode = FISSURE_MODES[parts[0]]
        filters = parts[1:]
        if len(filters) > 3:
            raise ValueError("裂缝最多支持地区、任务类型、纪元三种条件混合。")
        tier = planet = mission = ""
        for token in filters:
            if token in TIERS and not tier:
                tier = token
            elif token in PLANETS and not planet:
                planet = token
            elif token in MISSIONS and not mission:
                mission = "歼灭" if token == "殲滅" else token
            else:
                raise ValueError(
                    "未知或重复的裂缝条件：" + token +
                    "；支持地区、任务类型、纪元，例：订阅 钢铁裂缝 塞德娜 生存"
                )
        return RuleSpec("fissure", {
            "mode": mode, "tier": tier, "planet": planet, "mission": mission
        })
    if value == "仲裁":
        return RuleSpec("arbitration", {})
    if value in {"扎里曼", "圣所", "1999"}:
        return RuleSpec("bounty", {"region": value})
    if value == "阿耶":
        return RuleSpec("aya", {})
    if parts and parts[0].lower() == "wm":
        if len(parts) != 2 or not USER_ID.fullmatch(parts[1]):
            raise ValueError("用法：订阅 wm 市场用户名（用户名/个人主页 slug）")
        return RuleSpec("market_user", {"user": parts[1].lower()})
    riven = RIVEN_PATTERN.fullmatch(value)
    if riven:
        maximum = int(riven.group(2))
        if maximum < 1 or maximum > 9999999:
            raise ValueError("紫卡价格上限应为 1–9999999 白金。")
        return RuleSpec("riven", {"query": riven.group(1), "price": maximum})
    raise ValueError(
        "用法：订阅 夜灵 / 裂缝 [地区 任务 纪元] / 钢铁裂缝 [...] / "
        "九重天 [...] / 仲裁 / 扎里曼 / 圣所 / 1999 / 阿耶 / "
        "wm 用户ID / wmr 武器 词条 价格上限"
    )


def describe(kind: str, rule: dict) -> str:
    if kind == "cetus_night":
        return "夜灵平野 · 黑夜前 15 分钟"
    if kind == "fissure":
        mode = rule.get("mode", "steel" if rule.get("hard") else "normal")
        name = {"normal": "普通裂缝", "steel": "钢铁裂缝", "railjack": "九重天"}.get(
            mode, "裂缝"
        )
        return name + " · " + " ".join(filter(None, (
            rule.get("planet", ""), rule.get("mission", ""), rule.get("tier", "")
        ))) if any(rule.get(k) for k in ("planet", "mission", "tier")) else name
    if kind == "arbitration":
        return "仲裁 · S级 · 提前15分钟"
    if kind == "bounty":
        return "高效赏金 · " + rule.get("region", "未知")
    if kind == "aya":
        return "阿耶 · 地球三帐篷"
    if kind == "market_user":
        return "Market 排名 · " + rule.get("name", rule.get("user", ""))
    if kind == "riven":
        return "紫卡市场 · " + rule.get("weapon", "") + " · 低于" + str(
            rule.get("price", "?")
        ) + "白金"
    if kind == "market":
        return "旧版 Market 订阅（请取消并重新订阅）"
    return kind


def next_cetus_occurrence(
    cycle: CycleState, now: datetime, created_at: datetime
) -> Occurrence:
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
        key="cetus-night:" + night_at.isoformat(), due_at=due_at, event_at=night_at
    )
