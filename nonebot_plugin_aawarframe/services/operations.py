# 作用：解析每日突击、每周执刑官与当前入侵，整理任务、奖励和进度。
# 编写日期：2026-11-13
# 作者：Aameow

from datetime import datetime

from ..localization.resolver import load_mapping, node_info, translate
from ..models.common import Card, DataStatus, Snapshot
from ..models.operations import InvasionDisplay, OperationBoard, OperationTask
from ..models.worldstate import Invasion, Sortie, SortieMission
from ..worldstate.parsers.common import ParseError, records
from .common import card_for
from .cycles import remaining_clock


def faction_name(value: str) -> str:
    return {"FC_INFESTATION": "感染者", "Infestation": "感染者", "Infested": "感染者"}.get(
        value, translate(value)
    )


def build_sortie(snapshot: Snapshot, now: datetime, *, archon: bool = False) -> Card:
    card = card_for(snapshot, "执刑官猎杀" if archon else "每日突击")
    board = OperationBoard(kind="archon" if archon else "sortie")
    card.operation_board = board
    sorties, warnings = records(snapshot.data, "LiteSorties" if archon else "Sorties", Sortie)
    active = [item for item in sorties if item.activation <= now < item.expiry]
    if not active:
        card.status = DataStatus.EMPTY
        return card
    current = max(active, key=lambda item: item.activation)
    data = load_mapping("operations_zh.json")
    boss = data["bosses"].get(current.boss, {})
    board.boss = boss.get("name", current.boss)
    board.faction = faction_name(boss.get("faction", ""))
    board.expiry = current.expiry
    delta = current.expiry - now
    board.remaining = (
        f"{delta.days}天 {delta.seconds // 3600:02}:{delta.seconds // 60 % 60:02}"
        if delta.days
        else remaining_clock(current.expiry, now)
    )
    if archon:
        shard = data["shards"].get(current.boss)
        board.reward = shard["name"] if shard else "源力石类型暂缺"
        board.tone = shard["tone"] if shard else ""
    for number, raw in enumerate(current.missions if archon else current.variants, 1):
        try:
            mission = SortieMission.model_validate(raw)
        except (ValueError, TypeError):
            warnings.append("mission")
            continue
        node = node_info(mission.node)
        board.tasks.append(
            OperationTask(
                number=number,
                mission=translate(mission.mission_type),
                node=node["name"],
                planet=node.get("systemName", ""),
                modifier=data["modifiers"].get(mission.modifier, mission.modifier),
            )
        )
    if not board.tasks:
        raise ParseError("本期任务列表无有效记录")
    if warnings:
        card.notes.append("部分任务暂时无法显示。")
    return card


def reward_lines(raw: dict | list) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, dict):
        return ["奖励数据暂缺"]
    names = load_mapping("operations_zh.json")["rewards"]
    weekly_names = load_mapping("weekly_names.json")

    def name_for(item: str) -> str:
        path = item.replace("/Lotus/StoreItems/", "/Lotus/")
        return names.get(path) or weekly_names.get(path.lower()) or path.rsplit("/", 1)[-1]

    result = []
    counted = raw.get("countedItems", [])
    items = raw.get("items", [])
    if not isinstance(counted, list) or not isinstance(items, list):
        return ["奖励数据暂缺"]
    for item in counted:
        if not isinstance(item, dict) or not isinstance(item.get("ItemType"), str):
            result.append("奖励数据暂缺")
            continue
        quantity = item.get("ItemCount")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            result.append("奖励数据暂缺")
            continue
        result.append(f"{name_for(item['ItemType'])} ×{quantity}")
    for item in items:
        result.append(name_for(item) if isinstance(item, str) else "奖励数据暂缺")
    credits = raw.get("credits", 0)
    if isinstance(credits, int) and credits > 0:
        result.append(f"现金 ×{credits}")
    return result or ["奖励数据暂缺"]


def build_invasions(snapshot: Snapshot, now: datetime) -> Card:
    card = card_for(snapshot, "当前入侵")
    board = OperationBoard(kind="invasions")
    card.operation_board = board
    invasions, warnings = records(snapshot.data, "Invasions", Invasion)
    for invasion in invasions:
        if invasion.completed or invasion.activation > now:
            continue
        infestation = invasion.attacker == "FC_INFESTATION"
        # WFCD：普通对抗从 50% 开始；感染者从 100% 开始，随清除向 0% 下降。
        percent = min(
            100, max(0, (1 + invasion.count / invasion.goal) * (100 if infestation else 50))
        )
        node = node_info(invasion.node)
        board.invasions.append(
            InvasionDisplay(
                node=node["name"],
                planet=node.get("systemName", ""),
                attacker=faction_name(invasion.attacker),
                defender=faction_name(invasion.defender),
                attacker_percent=percent,
                defender_percent=100 - percent,
                attacker_rewards=reward_lines(invasion.attacker_reward),
                defender_rewards=reward_lines(invasion.defender_reward),
                infestation=infestation,
            )
        )
    board.invasions.sort(key=lambda item: (item.planet, item.node))
    if warnings:
        card.notes.append("部分入侵暂时无法显示。")
    if not board.invasions:
        card.status = DataStatus.EMPTY
    return card
