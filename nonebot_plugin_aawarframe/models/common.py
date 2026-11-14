# Desc: 定义共享快照、状态卡片与展示数据。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .arbitration import ArbitrationBoard
from .bounties import BountyDisplay
from .market import MarketBoard
from .operations import OperationBoard
from .riven_values import RivenValuesBoard
from .void_trader import TraderBoard


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    PARSE_ERROR = "parse_error"
    UNAVAILABLE = "unavailable"


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: Any
    source: str
    fetched_at: datetime = Field(default_factory=utcnow)
    stale: bool = False


class Section(BaseModel):
    highlighted_rows: list[int] = Field(default_factory=list)
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CycleDisplay(BaseModel):
    name: str
    state: str
    next_state: str = "—"
    remaining: str = "—"
    remaining_short: str = "—"
    expiry: datetime | None = None
    tone: str = "neutral"
    available: bool = True


class FissureDisplay(BaseModel):
    tier: str
    tier_key: str
    node: str
    planet: str
    mission: str
    faction: str
    remaining: str
    remaining_short: str = ""
    expiry: datetime
    urgent: bool = False


class Card(BaseModel):
    riven_values_board: RivenValuesBoard | None = None
    trader_board: TraderBoard | None = None
    arbitration_board: ArbitrationBoard | None = None
    market_board: MarketBoard | None = None
    title: str
    source: str
    fetched_at: datetime = Field(default_factory=utcnow)
    status: DataStatus = DataStatus.OK
    stale: bool = False
    sections: list[Section] = Field(default_factory=list)
    operation_board: OperationBoard | None = None
    cycle_items: list[CycleDisplay] = Field(default_factory=list)
    fissure_items: list[FissureDisplay] = Field(default_factory=list)
    fissure_mode: str = ""
    item_total: int = 0
    weekly_mode: bool = False
    rotation_expiry: datetime | None = None
    nightwave_mode: bool = False
    archimedea_mode: bool = False
    archimedea_activation: datetime | None = None
    archimedea_expiry: datetime | None = None
    archimedea_remaining: str = ""
    bounty_mode: bool = False
    bounty_detail: bool = False
    bounty_challenge_mode: bool = False
    bounty_region: str = "夜灵平野 · 希图斯"
    bounty_currency: str = "基础声望"
    bounty_items: list[BountyDisplay] = Field(default_factory=list)
    bounty_locations: dict[str, list[str]] = Field(default_factory=dict)
    bounty_expiry: datetime | None = None
    bounty_remaining: str = ""
    notes: list[str] = Field(default_factory=list)

    page_number: int | None = Field(default=None, ge=1)
    total_pages: int | None = Field(default=None, ge=1)

    def text(self) -> str:
        lines = [self.title]
        if self.riven_values_board:
            lines.append("词条修正：" + self.riven_values_board.layout)
            for variant in self.riven_values_board.variants:
                lines.append(variant.name)
                for title, attributes in [("普通词条", variant.ordinary), ("融合词条", variant.spliced)]:
                    lines.append(title)
                    lines.extend(f"{a.name}：正面 {a.positive} / 负面 {a.negative}" for a in attributes)
        if self.stale:
            lines.append("【过期缓存】上游暂不可用，请留意数据时间。")
        if self.archimedea_expiry:
            lines.append(f"本期剩余 {self.archimedea_remaining}")
        lines.extend(self.notes)
        if self.trader_board:
            lines.extend(filter(None, [self.trader_board.location, self.trader_board.message]))
            for group in self.trader_board.groups:
                lines.append(group.name)
                lines.extend(f"{item.name}：{item.ducats} 杜卡德 / {item.credits} 现金" for item in group.items)
        if self.arbitration_board:
            for item in self.arbitration_board.entries:
                lines.append(
                    f"{item.time.astimezone(timezone(timedelta(hours=8))):%m-%d %H:%M} {item.node} / {item.planet} · {item.mission} · {item.faction}"
                )
        if self.market_board:
            board = self.market_board
            if board.description:
                lines.append(board.description)
            if board.rank is not None:
                lines.append(f"等级：{board.rank} / {board.max_rank}")
            for title, orders in [("卖家", board.sell), ("买家", board.buy)]:
                lines.append(title)
                for order in orders:
                    status = "游戏中" if order.user.status == "ingame" else "在线"
                    lines.append(
                        f"{order.user.name} · {status} · 库存 {order.quantity} · 每次 {order.per_trade} · 单价 {order.platinum / order.per_trade:g} 白金"
                    )
                if not orders:
                    lines.append("暂无符合条件的在线挂单。")
        if self.operation_board:
            board = self.operation_board
            lines.extend(value for value in [board.boss, board.faction, board.reward] if value)
            if board.expiry:
                lines.append(f"剩余 {board.remaining}")
            for task in board.tasks:
                lines.append(
                    f"{task.number}. {task.mission} · {task.node} / {task.planet} · {task.modifier}"
                )
            for invasion in board.invasions:
                lines.append(f"{invasion.node} / {invasion.planet}")
                lines.append(
                    f"{invasion.attacker} {invasion.attacker_percent:.1f}%："
                    + "、".join(invasion.attacker_rewards)
                )
                lines.append(
                    f"{invasion.defender} {invasion.defender_percent:.1f}%："
                    + "、".join(invasion.defender_rewards)
                )
        for cycle in self.cycle_items:
            lines.append(
                f"{cycle.name}：{cycle.state}；{cycle.remaining}后切换至{cycle.next_state}"
                if cycle.available
                else f"{cycle.name}：暂时无法获取状态"
            )
        if self.fissure_mode and not self.fissure_items:
            lines.append("当前暂无任务。")
        for item in self.fissure_items:
            lines.append(
                f"{item.tier} · {item.mission} · {item.node} / {item.planet} · {item.faction} · 剩余 {item.remaining}"
            )
        for bounty in self.bounty_items:
            lines.append(
                f"{bounty.index}. {bounty.name} · {bounty.kind} · 等级 {bounty.min_level}–{bounty.max_level}"
            )
            lines.append(
                f"{self.bounty_currency}：{bounty.standing if bounty.standing is not None else '—'}"
            )
            if bounty.node:
                lines.append(f"{bounty.mission} · {bounty.node} · {bounty.faction}")
            lines.extend(bounty.objectives)
            if bounty.ally:
                lines.append(f"同行：{bounty.ally} · 好感度 +{bounty.chemistry}")
            if self.bounty_detail:
                for reward in bounty.rewards:
                    chances = " / ".join(
                        f"{value * 100:.2f}%" if value is not None else "—"
                        for value in reward.chances
                    )
                    lines.append(f"{reward.name} ×{reward.quantity}：{chances}")
                for stage, tasks in enumerate(bounty.task_pools, 1):
                    lines.append(f"任务池 {stage}：" + "、".join(tasks))
                if bounty.task_pool_note:
                    lines.append(bounty.task_pool_note)
            if bounty.message:
                lines.append(bounty.message)
        for location, jobs in self.bounty_locations.items():
            lines.append(f"{location}：" + "、".join(jobs))
        for section in self.sections:
            lines.append(section.title)
            if section.columns:
                lines.append(" | ".join(section.columns))
            lines.extend(" | ".join(row) for row in section.rows)
            lines.extend(section.notes)
        lines.append(f"来源：{self.source}")
        lines.append(f"获取时间：{self.fetched_at:%Y-%m-%d %H:%M:%S} UTC")
        return "\n".join(lines)
