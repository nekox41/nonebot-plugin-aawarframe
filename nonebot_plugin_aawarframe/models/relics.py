# Desc: 定义部件掉落遗物和遗物奖励价格卡片。
# Date: 2026-11-15
# Author: Aameow

from pydantic import BaseModel, Field


class RelicReference(BaseModel):
    name: str
    rarity: str
    vaulted: bool


class PartRelics(BaseModel):
    name: str
    quantity: int = 1
    relics: list[RelicReference] = Field(default_factory=list)


class PartsBoard(BaseModel):
    parts: list[PartRelics]


class RelicReward(BaseModel):
    ref: str
    name: str
    slug: str = ""
    quantity: int = 1
    chances: list[float | None]
    price: float | None = None
    price_status: str = "不可交易"


class RelicBoard(BaseModel):
    name: str
    vaulted: bool
    rewards: list[RelicReward]
