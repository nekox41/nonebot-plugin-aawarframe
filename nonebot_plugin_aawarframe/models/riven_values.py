# Desc: 定义紫卡词条范围和武器变体卡片。
# Date: 2026-11-14
# Author: Aameow

from pydantic import BaseModel, Field


class RivenAttribute(BaseModel):
    name: str
    positive: str
    negative: str


class RivenVariant(BaseModel):
    name: str
    weapon_class: str
    ordinary: list[RivenAttribute] = Field(default_factory=list)
    spliced: list[RivenAttribute] = Field(default_factory=list)


class RivenValuesBoard(BaseModel):
    layout: str
    variants: list[RivenVariant]
