# 作用：定义突击、执刑官与入侵卡片的展示结构。
# 编写日期：2026-11-13
# 作者：Aameow

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OperationTask(BaseModel):
    number: int
    mission: str
    node: str
    planet: str = ""
    modifier: str = ""


class InvasionDisplay(BaseModel):
    node: str
    planet: str
    attacker: str
    defender: str
    attacker_percent: float = Field(ge=0, le=100)
    defender_percent: float = Field(ge=0, le=100)
    attacker_rewards: list[str] = Field(default_factory=list)
    defender_rewards: list[str] = Field(default_factory=list)
    infestation: bool = False


class OperationBoard(BaseModel):
    kind: Literal["sortie", "archon", "invasions"]
    boss: str = ""
    faction: str = ""
    reward: str = ""
    tone: str = ""
    expiry: datetime | None = None
    remaining: str = ""
    tasks: list[OperationTask] = Field(default_factory=list)
    invasions: list[InvasionDisplay] = Field(default_factory=list)
