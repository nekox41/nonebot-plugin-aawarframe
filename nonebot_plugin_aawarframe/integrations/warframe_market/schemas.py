from typing import Literal, Union, Optional, List, Dict

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class UserShort(BaseModel):
    id: str
    ingameName: str
    slug: str
    reputation: int
    platform: str
    crossplay: bool
    locale: str
    status: str
    avatar: Optional[str] = None
    lastSeen: str

class Order(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    platinum: int
    quantity: int
    perTrade: Optional[int] = None
    subtype: Optional[str] = None
    rank: Optional[int] = None
    charges: Optional[int] = None
    amberStars: Optional[int] = None
    cyanStars: Optional[int] = None
    visible: bool
    createdAt: datetime
    updatedAt: datetime
    itemId: Optional[str] = None
    groupId: Optional[str] = None
    user: Optional[UserShort] = None

    def is_sell(self) -> bool:
        return self.type == "sell"

    def is_buy(self) -> bool:
        return self.type == "buy"

    def is_ingame(self) -> bool:
        """
        检测创建订单的用户是否处于 ingame 状态
        :return:
        """
        if self.user is None:
            return False
        return self.user.status == "ingame"

    def __str__(self) -> str:
        return f"{self.user.ingameName if self.user is not None else "无"}({self.user.status if self.user is not None else "无"}) - {self.itemId if self.itemId is not None else "无"} - {self.platinum}"

class ItemI18N(BaseModel):
    name: str
    description: Optional[str] = None
    wikiLink: Optional[str] = None
    icon: str
    thumb: str
    subIcon: Optional[str] = None

class Item(BaseModel):
    id: str
    slug: str
    gameRef: str
    tags: List[str]
    setRoot: Optional[bool] = None
    setParts: Optional[List[str]] = None
    quantityInSet: Optional[int] = None
    rarity: Optional[str] = None
    bulkTradable: Optional[bool] = None
    subtypes: Optional[List[str]] = None
    maxRank: Optional[int] = None
    maxCharges: Optional[int] = None
    maxAmberStars: Optional[int] = None
    maxCyanStars: Optional[int] = None
    baseEndo: Optional[int] = None
    endoMultiplier: Optional[int] = None
    ducats: Optional[int] = None
    vosfor: Optional[int] = None
    reqMasteryRank: Optional[int] = None
    vaulted: Optional[bool] = None
    tradingTax: Optional[int] = None
    i18n: Optional[Dict[str, ItemI18N]] = None
    tradable: Optional[bool] = None


# ---------- 已成交统计（Closed） ----------
class ClosedStatistic(BaseModel):
    """单条已成交/已关闭订单的统计记录"""
    datetime: datetime
    volume: int
    min_price: float
    max_price: float
    open_price: float
    closed_price: float
    avg_price: float
    wa_price: float
    median: float
    moving_avg: Optional[float] = None   # 某些记录可能没有该字段
    donch_top: float
    donch_bot: float
    id: str
    mod_rank: Optional[int] = None


class LiveStatistic(BaseModel):
    """单条实时挂单统计记录（区分买单/卖单）"""
    datetime: datetime
    volume: int
    min_price: float
    max_price: float
    avg_price: float
    wa_price: float
    median: float
    order_type: Literal["buy", "sell"]
    moving_avg: Optional[float] = None
    id: str
    mod_rank: Optional[int] = None



class StatisticsClosed(BaseModel):
    """已成交统计，按时间窗口分组"""
    forty_eight_hours: List[ClosedStatistic] = Field(alias="48hours")
    ninety_days: List[ClosedStatistic] = Field(alias="90days")

    model_config = {"populate_by_name": True}   # 允许使用字段名访问


class StatisticsLive(BaseModel):
    """实时挂单统计，按时间窗口分组"""
    forty_eight_hours: List[LiveStatistic] = Field(alias="48hours")
    ninety_days: List[LiveStatistic] = Field(alias="90days")

    model_config = {"populate_by_name": True}


class ItemStatistics(BaseModel):
    """Warframe Market 物品统计接口的完整响应"""
    statistics_closed: StatisticsClosed
    statistics_live: StatisticsLive

