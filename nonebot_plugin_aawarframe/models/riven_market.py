# Desc: 定义紫卡拍卖搜索条件和挂单卡片。
# Date: 2026-11-14
# Author: Aameow

from pydantic import BaseModel, Field


class RivenMarketQuery(BaseModel):
    weapon: str
    positives: list[str] = Field(default_factory=list)
    negative: str | None = None

    @property
    def unrolled(self):
        return not self.positives and self.negative is None


class RivenListing(BaseModel):
    seller: str
    status: str
    price: int
    price_type: str
    rank: int
    mastery: int
    rolls: int
    positives: list[str]
    negatives: list[str]


class RivenMarketBoard(BaseModel):
    weapon: str
    positive_filter: str
    negative_filter: str
    listings: list[RivenListing] = Field(default_factory=list)
