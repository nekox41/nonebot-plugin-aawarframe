"""将共享世界状态、仲裁排期和 Market 快照转换为稳定订阅事件。"""

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from ..localization.resolver import node_info
from ..models.market import MarketQuery
from ..models.worldstate import Fissure, SyndicateJob, SyndicateMission
from ..services.bounties import bounty_kind
from ..services.fissures import TIERS
from ..services.market import MarketService
from ..worldstate.parsers.common import records

# 保留旧版赏金解析辅助函数的映射，不再开放这些命令。
REGIONS = {
    "地球": "CetusSyndicate",
    "金星": "SolarisSyndicate",
    "火卫二": "EntratiSyndicate",
    "圣所": "EntratiLabSyndicate",
    "扎里曼": "ZarimanSyndicate",
    "1999": "HexSyndicate",
}

BEIJING = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Event:
    key: str
    title: str
    detail: str
    due_at: datetime
    event_at: datetime


def _key(prefix: str, *values: object) -> str:
    raw = "|".join(str(v) for v in values)
    return prefix + ":" + sha256(raw.encode("utf-8")).hexdigest()


def fissure_events(data: dict, now: datetime, rule: dict) -> tuple[list[Event], str]:
    """区分普通、钢铁、九重天，支持地区/任务/纪元交叉筛选。"""
    from ..models.worldstate import VoidStorm

    mode = rule.get("mode", "steel" if rule.get("hard") else "normal")
    if mode == "railjack":
        missions, _ = records(data, "VoidStorms", VoidStorm)
    elif mode in {"normal", "steel"}:
        raw, _ = records(data, "ActiveMissions", Fissure)
        missions = [m for m in raw if m.hard == (mode == "steel")]
    else:
        raise ValueError("无效裂缝分类")
    matched = []
    for mission in missions:
        if not mission.activation <= now < mission.expiry:
            continue
        tier = TIERS.get(mission.modifier, mission.modifier)
        if rule.get("tier") and tier != rule["tier"]:
            continue
        node = node_info(mission.node)
        mission_type = str(node.get("missionName", "未知任务"))
        planet = str(node.get("systemName", "未知星球"))
        if rule.get("mission") and rule["mission"] != mission_type:
            continue
        wanted_planet = rule.get("planet")
        if wanted_planet and not (
            wanted_planet == planet or (
                mode == "railjack" and planet.startswith(wanted_planet)
            )
        ):
            continue
        detail = (
            f"{tier} · {planet} / {node.get('name', mission.node)} · {mission_type}"
            f" · 北京时间 {mission.expiry.astimezone(BEIJING):%H:%M} 结束"
        )
        title = {"normal": "发现普通虚空裂缝", "steel": "发现钢铁裂缝",
                 "railjack": "发现九重天虚空风暴"}[mode]
        matched.append(Event(
            key=_key("fissure", mode, mission.node, mission.modifier,
                     mission.activation.isoformat(), mission.expiry.isoformat()),
            title=title, detail=detail, due_at=now, event_at=mission.activation,
        ))
    label = {"normal": "普通裂缝", "steel": "钢铁裂缝", "railjack": "九重天"}[mode]
    return matched, f"{label}符合 {len(matched)} 项" if matched else f"{label}暂无匹配"

def bounty_events(data: dict, now: datetime, rule: dict) -> tuple[list[Event], str]:
    missions, _ = records(data, "SyndicateMissions", SyndicateMission)
    tag = REGIONS[rule["region"]]
    result = []
    for mission in missions:
        if mission.tag != tag or not mission.activation <= now < mission.expiry:
            continue
        jobs, _ = records({"Jobs": mission.jobs}, "Jobs", SyndicateJob)
        kinds = sorted({bounty_kind(job) for job in jobs})
        if rule.get("type") and rule["type"] not in kinds:
            continue
        category = rule.get("type") or ("、".join(kinds) if kinds else "新一轮任务")
        detail = (
            f"{rule['region']}赏金已轮换 · {category}"
            f" · 北京时间 {mission.expiry.astimezone(BEIJING):%m-%d %H:%M} 截止"
        )
        result.append(Event(
            key=_key("bounty", tag, mission.activation.isoformat(),
                     mission.expiry.isoformat(), rule.get("type", "")),
            title=f"{rule['region']}赏金更新", detail=detail,
            due_at=now, event_at=mission.activation,
        ))
    status = f"{rule['region']}赏金正在轮换" if result else f"{rule['region']}赏金暂无匹配"
    return result, status


def arbitration_events(
    schedule: list, nodes: dict, now: datetime, created_at: datetime, rule: dict,
    stats=None,
) -> tuple[list[Event], str]:
    """仅 S 级仲裁，在开场前 15 分钟提示（排期必须已知）。"""
    starts = [r[0] for r in schedule]
    index = bisect.bisect_left(starts, int((now - timedelta(minutes=16)).timestamp()))
    matches = []
    next_time = None
    for start, node_id in schedule[index:]:
        at = datetime.fromtimestamp(start, timezone.utc)
        if at > now + timedelta(hours=24):
            break
        node = nodes.get(node_id)
        if not node:
            continue
        grade = stats(node_id) if stats is not None else node.get("arbitration") or {}
        if not grade or grade.get("grade") != "S":
            continue
        if at <= now:
            continue
        if next_time is None:
            next_time = at
        due = at - timedelta(minutes=15)
        if due < created_at or due < now - timedelta(seconds=90):
            continue
        detail = (
            f"S 级 · {node.get('missionName', '仲裁')} · "
            f"{node.get('systemName', '')} / {node.get('name', node_id)} · "
            f"北京时间 {at.astimezone(BEIJING):%m-%d %H:%M} 开始"
        )
        matches.append(Event(
            key=_key("arbitration-s", start, node_id),
            title="S 级仲裁将在15分钟后开始", detail=detail,
            due_at=due, event_at=at,
        ))
    status = (
        f"下场 S 级 {next_time.astimezone(BEIJING):%m-%d %H:%M}"
        if next_time else "未来24小时暂无 S 级仲裁"
    )
    return matches, status

def market_events(top, now: datetime, rule: dict) -> tuple[list[Event], str]:
    query = MarketQuery(
        name=rule["name"], rank=rule.get("rank"),
        subtype=rule.get("subtype"), platform="pc", crossplay=True,
    )
    visible = [
        order for order in top.sell
        if order.type == "sell" and MarketService.visible(order, query)
    ]
    limit = rule["price"]
    qualified = sorted(
        (order for order in visible if order.platinum / order.per_trade <= limit),
        key=lambda order: (order.platinum / order.per_trade, order.id),
    )
    events = []
    for order in qualified:
        price = order.platinum / order.per_trade
        detail = (
            f"{rule['name']} · {price:g} 白金/个 · "
            f"{order.user.name} · 库存 {order.quantity}"
        )
        events.append(Event(
            key="market-order:" + order.id, title="发现符合条件的 Market 卖单",
            detail=detail, due_at=now, event_at=now,
        ))
    if visible:
        cheapest = min(o.platinum / o.per_trade for o in visible)
        status = f"当前最低 {cheapest:g} 白金 · 符合 {len(qualified)} 单"
    else:
        status = "当前暂无在线卖单"
    return events, status
