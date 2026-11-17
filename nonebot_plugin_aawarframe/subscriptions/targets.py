"""定向赏金、阿耶、Market 用户排名和紫卡价格条件的结构化事件。"""

from datetime import datetime
from hashlib import sha256

from ..models.common import Snapshot
from ..services.bounties import build_bounties
from .sources import BEIJING, Event

REGIONS = {"扎里曼": "zariman", "圣所": "sanctum", "1999": "hex"}
SKILL_BLOCKERS = ("禁用技能", "禁止使用技能", "无法使用技能", "不可使用技能",
                  "禁用战甲技能", "不使用技能")


def _event_key(prefix: str, *values: object) -> str:
    return prefix + ":" + sha256("|".join(map(str, values)).encode()).hexdigest()


def _quick_bounty(item, region: str) -> bool:
    context = " ".join([item.name, item.mission, *item.objectives])
    blocked = any(keyword in context for keyword in SKILL_BLOCKERS) or (
        "技能" in context and ("禁用" in context or "禁止" in context)
    )
    if blocked:
        return False
    extermination = "歼灭" in item.mission
    if region in {"扎里曼", "圣所"}:
        return item.index in {4, 5} and extermination
    # 1999：5级或杀毒赏金的歼灭；另外支持“捕获传承种 + 找到保险箱”
    if extermination and (item.index == 5 or item.kind == "杀毒"):
        return True
    capture = "传承种" in context and "捕获" in context
    safe = "保险箱" in context and any(
        word in context for word in ("寻找", "找到", "搜索", "发现", "定位")
    )
    return capture and safe


def efficient_bounty_events(
    snapshot: Snapshot, now: datetime, rule: dict
) -> tuple[list[Event], str]:
    region = rule["region"]
    card = build_bounties(snapshot, now, region=REGIONS[region])
    if card.bounty_expiry is None:
        return [], region + "赏金暂无有效轮换"
    # 从任务本身构建 ID；同一轮有多个匹配任务时单独记录，保证提醒具体。
    events = []
    for item in card.bounty_items:
        if not _quick_bounty(item, region):
            continue
        description = "；".join(item.objectives[:3])
        detail = (
            f"{region}赏金 {item.index} · {item.mission} · {item.node} · "
            + (description or item.name)
            + f" · {card.bounty_expiry.astimezone(BEIJING):%m-%d %H:%M} 结束"
        )
        events.append(Event(
            key=_event_key("quick-bounty", region, card.bounty_expiry.isoformat(),
                           item.index, item.node, item.name),
            title=f"{region}高效赏金已出现", detail=detail,
            due_at=now, event_at=now,
        ))
    status = f"{region}当前符合 {len(events)} 项" if events else f"{region}本轮无高效赏金"
    return events, status


def aya_events(snapshot: Snapshot, now: datetime) -> tuple[list[Event], str]:
    card = build_bounties(snapshot, now, region="earth")
    if card.bounty_expiry is None or not card.bounty_locations:
        raise ValueError("地球平原三个帐篷任务数据不完整")
    wanted = ("搜索并救援", "捕获 Grineer 特工")
    found = []
    for tent, jobs in card.bounty_locations.items():
        for job in jobs:
            normalized = " ".join(job.casefold().split())
            if any(" ".join(name.casefold().split()) in normalized for name in wanted):
                found.append((tent, job))
    if not found:
        return [], "三个帐篷暂未出现阿耶速刷任务"
    detail = "；".join(f"{tent}：{job}" for tent, job in found)
    detail += f" · 本轮 {card.bounty_expiry.astimezone(BEIJING):%H:%M} 结束"
    event = Event(
        key=_event_key("aya-tents", card.bounty_expiry.isoformat()),
        title="地球平原阿耶速刷任务已出现", detail=detail,
        due_at=now, event_at=now,
    )
    return [event], f"阿耶任务已出现：{len(found)} 项"


def _unit_price(order: dict) -> float:
    quantity = order.get("perTrade", 1) or 1
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("无效的每笔数量")
    return order["platinum"] / quantity


def market_rank_events(
    user_orders: list[dict], item_orders: dict[str, list[dict]],
    now: datetime, labels: dict[str, str] | None = None,
) -> tuple[list[Event], str]:
    """将同品级/子类型订单按可交易单价比较；同最低价视作并列第一。"""
    results = []
    checked = 0
    for own in user_orders:
        if own.get("type") != "sell" or not own.get("visible", False):
            continue
        item_id = own.get("itemId")
        if not item_id or item_id not in item_orders:
            continue
        checked += 1
        try:
            own_price = _unit_price(own)
        except (KeyError, ValueError, TypeError):
            continue
        comparisons = []
        for other in item_orders[item_id]:
            if other.get("type") != "sell" or not other.get("visible", False):
                continue
            if other.get("id") == own.get("id"):
                continue
            if any(other.get(k) != own.get(k) for k in
                   ("rank", "subtype", "charges", "amberStars", "cyanStars")):
                continue
            user = other.get("user") or {}
            if user.get("status") not in {"online", "ingame"}:
                continue
            try:
                comparisons.append(_unit_price(other))
            except (ValueError, TypeError, KeyError):
                pass
        if not comparisons or min(comparisons) >= own_price:
            continue
        best = min(comparisons)
        label = (labels or {}).get(item_id, item_id)
        results.append(Event(
            key="market-rank:" + str(own["id"]),
            title="Market 卖单已失去最低价位置",
            detail=f"{label} · 我的卖价 {own_price:g} 白金 · "
                   f"当前其他玩家最低 {best:g} 白金",
            due_at=now, event_at=now,
        ))
    status = f"检查 {checked} 单 · 有 {len(results)} 单不是最低价"
    return results, status


def riven_events(
    rows: list[dict], now: datetime, rule: dict
) -> tuple[list[Event], str]:
    wanted = set(rule["positives"])
    negative = rule.get("negative")
    matched = []
    for row in rows:
        if not isinstance(row, dict) or row.get("closed") or row.get("private"):
            continue
        if not row.get("visible") or (
            row.get("platform") not in {"pc", None} and not row.get("crossplay")
        ):
            continue
        item = row.get("item") or {}
        if item.get("type") != "riven" or item.get("weapon_url_name") != rule["slug"]:
            continue
        attrs = item.get("attributes") or []
        positive = {
            a.get("url_name") for a in attrs if a.get("positive") is True
        }
        negatives = {
            a.get("url_name") for a in attrs if a.get("positive") is False
        }
        if not wanted <= positive or (
            negative == "has" and not negatives
        ) or (negative not in {None, "has"} and negative not in negatives):
            continue
        price = row.get("buyout_price")
        # 未设置买断价的拍卖不能把起拍价视作真实可买价。
        if not isinstance(price, int) or price >= rule["price"] or price < 0:
            continue
        auction_id = row.get("id")
        if not auction_id:
            continue
        owner = row.get("owner") or {}
        matched.append(Event(
            key="riven-auction:" + str(auction_id),
            title="发现低于价格上限的紫卡",
            detail=f"{rule['weapon']} · {price} 白金 · "
                   f"{owner.get('ingame_name', '未知卖家')}",
            due_at=now, event_at=now,
        ))
    return matched, f"当前找到 {len(matched)} 张符合条件的紫卡"
