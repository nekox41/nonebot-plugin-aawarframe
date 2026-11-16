# Desc: 定义 Market 成交统计和趋势卡片数据。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class SaleRecord(BaseModel):
    time: datetime = Field(alias="datetime")
    volume: int = Field(ge=0)
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    mod_rank: int | None = None
    subtype: str | None = None

    @model_validator(mode="before")
    @classmethod
    def average_price(cls, data):
        return {**data, "price": data.get("wa_price") if data.get("wa_price") is not None else data.get("avg_price")}

    @field_validator("time")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("统计时间缺少时区")
        return value


class TrendPoint(BaseModel):
    time: datetime
    volume: int = 0
    price: float | None = None


class TrendPeriod(BaseModel):
    title: str
    volume: int
    average: float | None
    points: list[TrendPoint]


class TrendBoard(BaseModel):
    name: str
    rank: int | None = None
    max_rank: int | None = None
    subtype: str = ""
    periods: list[TrendPeriod]
