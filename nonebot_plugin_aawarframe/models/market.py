from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ItemName(BaseModel):
    name: str


class Item(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    slug: str = Field(pattern=r"^[a-z0-9_]+$")
    game_ref: str = Field(default="", alias="gameRef")
    max_rank: int | None = Field(default=None, alias="maxRank", ge=0)
    subtypes: list[str] = Field(default_factory=list)
    i18n: dict[str, ItemName] = Field(default_factory=dict)
    tradable: bool = True

    def name(self, language: str = "zh-hans") -> str:
        localized = self.i18n.get(language) or self.i18n.get("en")
        return localized.name if localized else self.slug


class MarketUser(BaseModel):
    name: str = Field(alias="ingameName")
    status: str
    platform: str
    crossplay: bool = False


class Order(BaseModel):
    id: str
    type: Literal["buy", "sell"]
    platinum: int = Field(ge=0)
    quantity: int = Field(ge=1)
    per_trade: int = Field(default=1, alias="perTrade", ge=1)
    rank: int | None = None
    subtype: str | None = None
    charges: int | None = None
    amber_stars: int | None = Field(default=None, alias="amberStars")
    cyan_stars: int | None = Field(default=None, alias="cyanStars")
    visible: bool
    updated_at: datetime = Field(alias="updatedAt")
    user: MarketUser | None = None

    @field_validator("updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("订单更新时间缺少时区")
        return value


class MarketQuery(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_rank: bool = False
    rank: int | None = Field(default=None, ge=0)
    subtype: str | None = None
    platform: Literal["pc"] = "pc"
    crossplay: bool = True
