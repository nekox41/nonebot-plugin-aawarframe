"""固定的 WebUI 预览数据；不依赖机器人命令、网络请求或运行时缓存。"""
from datetime import datetime, timezone

from ..models.common import Card, CycleDisplay, FissureDisplay, Section
from ..models.operations import OperationBoard, OperationTask, InvasionDisplay
from ..models.relics import PartsBoard, PartRelics, RelicReference, RelicBoard, RelicReward
from ..models.market import MarketBoard, MarketUser, Order
from ..models.trend import TrendBoard, TrendPeriod, TrendPoint
from ..models.arbitration import ArbitrationBoard, ArbitrationEntry
from ..models.riven_market import RivenMarketBoard, RivenListing
from ..models.riven_values import RivenValuesBoard, RivenAttribute
from ..models.void_trader import TraderBoard, TraderGroup, TraderItem
from ..models.bounties import BountyDisplay, BountyReward

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def _card(title: str, **values) -> Card:
    return Card(title=title, source="AaWarframe · WebUI 固定预览数据", fetched_at=NOW, **values)


def _bounty(index: int = 1, *, challenge: bool = False) -> BountyDisplay:
    return BountyDisplay(
        index=index,
        name="夜灵平原赏金" if not challenge else "钢铁之路挑战",
        kind="常规" if not challenge else "挑战",
        min_level=40 if challenge else 20,
        max_level=60 if challenge else 40,
        stages=5,
        standing=10000,
        mastery=10,
        rotation="A",
        rewards=[BountyReward(name="稀有部件蓝图", quantity=1, chances=[0.25, 0.2, 0.15, 0.1, 0.05])],
        task_pools=[["解放营地", "破坏补给"], ["防御无人机", "刺杀目标"]],
        node="希图斯",
        mission="解放营地",
        faction="Grineer",
        objectives=["完成目标并撤离", "保护赏金目标"],
        ally="Konzu",
        chemistry=100,
    )


PREVIEW_CARDS: dict[str, Card] = {
    "card": _card(
        "通用信息卡片",
        sections=[Section(title="预览数据", columns=["项目", "内容"], rows=[["运行状态", "正常"], ["版本", "0.24.7"]], notes=["固定预览数据，不会请求外部接口。"])],
    ),
    "cycles": _card(
        "环境周期",
        cycle_items=[
            CycleDisplay(name="夜灵平原", state="白天", next_state="黑夜", remaining="12 分钟", remaining_short="12:00", expiry=LATER, tone="day"),
            CycleDisplay(name="奥布山谷", state="温暖", next_state="寒冷", remaining="18 分钟", remaining_short="18:00", expiry=LATER, tone="warm"),
        ],
    ),
    "fissures": _card(
        "虚空裂缝",
        fissure_mode="normal",
        item_total=2,
        fissure_items=[
            FissureDisplay(tier="古纪", tier_key="VoidT1", node="Everest", planet="地球", mission="挖掘", faction="Grineer", remaining="20 分钟", remaining_short="20:00", expiry=LATER),
            FissureDisplay(tier="中纪", tier_key="VoidT2", node="Hydron", planet="塞德娜", mission="防御", faction="Grineer", remaining="8 分钟", remaining_short="08:00", expiry=LATER, urgent=True),
        ],
    ),
    "arbitration": _card(
        "仲裁排期",
        arbitration_board=ArbitrationBoard(current=True, entries=[
            ArbitrationEntry(node_id="SolNode1", node="Everest", planet="地球", mission="挖掘", faction="Grineer", time=NOW, remaining="42 分钟", label="当前", grade="A", vitus_per_minute=1.5),
            ArbitrationEntry(node_id="SolNode2", node="Hydron", planet="塞德娜", mission="防御", faction="Grineer", time=LATER, remaining="", grade="B", vitus_per_minute=1.2),
        ]),
    ),
    "market": _card(
        "Warframe Market · Prime 战甲",
        market_board=MarketBoard(
            name="Saryn Prime", description="满级战甲部件交易示例", image="", rank=30, max_rank=30,
            sell=[Order(id="sell-1", type="sell", platinum=120, quantity=2, per_trade=1, visible=True, updatedAt=NOW, user=MarketUser.model_validate({"ingameName":"TennoSeller","status":"ingame","platform":"pc"}))],
            buy=[Order(id="buy-1", type="buy", platinum=95, quantity=1, perTrade=1, visible=True, updatedAt=NOW, user=MarketUser.model_validate({"ingameName":"TennoBuyer","status":"online","platform":"pc"}))],
        ),
    ),
    "sortie": _card(
        "每日突击",
        operation_board=OperationBoard(kind="sortie", boss="突击首领", faction="Grineer", reward="裂罅破解器", tone="gold", expiry=LATER, remaining="6 小时", tasks=[
            OperationTask(number=1, mission="歼灭", node="土星 · 卡西尼", planet="土星", modifier="敌人等级提升"),
            OperationTask(number=2, mission="防御", node="木星 · 卡梅里亚", planet="木星", modifier=""),
        ]),
    ),
    "archon": _card(
        "执刑官猎杀",
        operation_board=OperationBoard(kind="archon", boss="执刑官 Amar", faction="Sentient", reward="赤色执刑官碎片", tone="red", expiry=LATER, remaining="6 小时", tasks=[
            OperationTask(number=1, mission="破坏", node="地球 · 森林", planet="地球", modifier=""),
            OperationTask(number=2, mission="刺杀", node="地球 · 森林", planet="地球", modifier="执刑官战斗"),
        ]),
    ),
    "invasions": _card(
        "入侵任务",
        operation_board=OperationBoard(kind="invasions", invasions=[
            InvasionDisplay(node="Ceres · Draco", planet="谷神星", mission_type="生存", attacker="Grineer", defender="Corpus", attacker_percent=62.5, defender_percent=37.5, attacker_rewards=["Forma 蓝图"], defender_rewards=["Orokin 电池"]),
        ]),
    ),
    "parts": _card(
        "Prime 部件来源",
        parts_board=PartsBoard(parts=[
            PartRelics(name="Saryn Prime 机体", quantity=1, relics=[
                RelicReference(name="古纪 A1", rarity="common", vaulted=False),
                RelicReference(name="中纪 B2", rarity="rare", vaulted=True),
            ]),
        ]),
    ),
    "relics": _card(
        "古纪 A1 遗物奖励",
        relic_board=RelicBoard(name="古纪 A1", vaulted=False, rewards=[
            RelicReward(ref="A1", name="Prime 部件蓝图", chances=[25.33, 11, 2, 0.33], price=18.5),
            RelicReward(ref="A1", name="Forma 蓝图", chances=[25.33, 11, 2, 0.33], price=None, price_status="不可交易"),
        ]),
    ),
    "trend": _card(
        "Saryn Prime 成交趋势",
        trend_board=TrendBoard(name="Saryn Prime", rank=30, max_rank=30, subtype="Prime 战甲", periods=[
            TrendPeriod(title="近 7 天", volume=128, average=42.5, points=[
                TrendPoint(time=datetime(2026, 11, 14, tzinfo=timezone.utc), volume=12, price=40.0),
                TrendPoint(time=datetime(2026, 11, 17, tzinfo=timezone.utc), volume=18, price=43.0),
                TrendPoint(time=NOW, volume=21, price=42.5),
            ]),
        ]),
    ),
    "riven_analysis": _card(
        "伯斯顿 Prime 紫卡分析",
        analysis_mode=True,
        sections=[Section(title="词条分析", columns=["词条", "当前数值", "评级"], rows=[["多重射击", "+120%", "A"], ["暴击几率", "+150%", "S"]])],
    ),
    "attributes": _card(
        "紫卡词条缩写",
        attribute_rows=[("MS", "多重射击"), ("CC", "暴击几率"), ("CD", "暴击伤害"), ("元素", "元素伤害")],
    ),
    "commands": _card(
        "AaWarframe 命令列表",
        command_names=["/warframe cycles", "/warframe fissures", "/warframe market", "/warframe relics"],
    ),
    "riven_market": _card(
        "伯斯顿 Prime 紫卡市场",
        riven_market_board=RivenMarketBoard(weapon="伯斯顿 Prime", positive_filter="多重射击", negative_filter="无负面", listings=[
            RivenListing(seller="TennoSeller", status="在线", price=350, price_type="议价", rank=8, mastery=20, rolls=12, positives=["多重射击 +120%", "暴击几率 +95%"], negatives=[]),
        ]),
    ),
    "riven_values": _card(
        "伯斯顿 Prime 紫卡数值",
        riven_values_board=RivenValuesBoard(layout="2+1", name="伯斯顿 Prime", weapon_class="步枪", variants=["伯斯顿", "伯斯顿 Prime"], ordinary=[
            RivenAttribute(name="多重射击", positive="基准 ×1.00", negative="—"),
            RivenAttribute(name="暴击几率", positive="基准 ×1.00", negative="—"),
        ], spliced=[RivenAttribute(name="伤害", positive="基准 ×1.00", negative="—")]),
    ),
    "void_trader": _card(
        "虚空商人货单",
        trader_board=TraderBoard(location="中继站 · 水星", time=LATER, message="", groups=[
            TraderGroup(name="武器", items=[TraderItem(name="棱晶布拉顿", ducats=500, credits=300000)]),
            TraderGroup(name="Mod", items=[TraderItem(name="压迫点 Prime", ducats=350, credits=150000)]),
        ]),
    ),
    "weekly": _card(
        "每周轮换",
        weekly_mode=True,
        rotation_expiry=LATER,
        sections=[Section(title="每周奖励", columns=["周次", "奖励", "数量"], rows=[["本周", "赤毒", "1000"], ["下周", "内融核心", "50"]], highlighted_rows=[0])],
    ),
    "nightwave": _card(
        "午夜电波挑战",
        nightwave_mode=True,
        sections=[Section(title="每日挑战", rows=[["完成任务", "完成 3 场任务", "1000", "2 天", "每日"]]), Section(title="每周挑战", rows=[["精英周常", "完成 5 场中断任务", "7000", "5 天", "精英"]])],
    ),
    "archimedea": _card(
        "深层科研轮换",
        archimedea_mode=True,
        archimedea_activation=NOW,
        archimedea_expiry=LATER,
        archimedea_remaining="6 小时",
        sections=[Section(title="偏差条件", rows=[["偏差", "敌人强化", "敌人造成的伤害提高。"], ["精英风险", "能量枯竭", "能量恢复速度降低。"]])],
    ),
    "bounties": _card(
        "夜灵平原赏金",
        bounty_mode=True, bounty_detail=True, bounty_expiry=LATER, bounty_remaining="6 小时",
        bounty_items=[_bounty()],
    ),
    "challenge_bounties": _card(
        "挑战赏金",
        bounty_challenge_mode=True, bounty_detail=True, bounty_expiry=LATER, bounty_remaining="6 小时",
        bounty_items=[_bounty(challenge=True)],
    ),
}


def get_preview_card(feature: str) -> Card:
    """Return an isolated Card instance for a stable, offline feature preview."""
    if feature not in PREVIEW_CARDS:
        raise KeyError(feature)
    return Card.model_validate(PREVIEW_CARDS[feature].model_dump(mode="python", by_alias=True))
