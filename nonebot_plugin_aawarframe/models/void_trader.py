# Desc: 虚空商人原始货单与分组卡片。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime

from pydantic import BaseModel, Field

from .worldstate import WorldDate


class TraderOffer(BaseModel):
    type: str = Field(alias="ItemType", min_length=1)
    ducats: int = Field(alias="PrimePrice", ge=0)
    credits: int = Field(alias="RegularPrice", ge=0)


class VoidTrader(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    node: str = Field(alias="Node")
    manifest: list[TraderOffer] = Field(default_factory=list, alias="Manifest")


class TraderItem(BaseModel):
    name: str
    ducats: int
    credits: int
    location: str = ""


class TraderGroup(BaseModel):
    name: str
    items: list[TraderItem] = Field(default_factory=list)


class TraderBoard(BaseModel):
    location: str = ""
    time: datetime | None = None
    time_label: str = "离开时间"
    message: str = ""
    groups: list[TraderGroup] = Field(default_factory=list)
