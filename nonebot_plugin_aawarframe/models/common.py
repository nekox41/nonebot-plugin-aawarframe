# 作用：定义共享快照、状态卡片与展示数据。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .bounties import BountyDisplay


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
    title: str
    source: str
    fetched_at: datetime = Field(default_factory=utcnow)
    status: DataStatus = DataStatus.OK
    stale: bool = False
    sections: list[Section] = Field(default_factory=list)
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
    help_mode: bool = False
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
        if self.stale:
            lines.append("【过期缓存】上游暂不可用，请留意数据时间。")
        if self.archimedea_expiry:
            lines.append(f"本期剩余 {self.archimedea_remaining}")
        lines.extend(self.notes)
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
