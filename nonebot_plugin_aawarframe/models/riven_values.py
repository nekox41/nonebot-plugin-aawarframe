# Desc: 定义武器家族共用的紫卡词条数值卡片。
# Date: 2026-11-14
# Author: Aameow

from pydantic import BaseModel, Field


class RivenAttribute(BaseModel):
    name: str
    positive: str
    negative: str


class RivenValuesBoard(BaseModel):
    layout: str
    name: str
    weapon_class: str
    variants: list[str] = Field(default_factory=list)
    ordinary: list[RivenAttribute] = Field(default_factory=list)
    spliced: list[RivenAttribute] = Field(default_factory=list)
