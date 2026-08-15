from ...common import client
from typing import List
from .schemas import Order, Item, ItemStatistics

WM_API = "https://api.warframe.market/v2"
HEADERS = {
    "Language":"zh-hans"
}

async def fetch_orders(slug: str) -> List[Order]:
    """
    获取物品的所有订单
    :param slug:
    :return:
    """
    url = f"{WM_API}/orders/item/{slug}"
    response = await client.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    orders_data = data.get("data", [])
    return [Order(**order) for order in orders_data]

async def fetch_item(slug: str) -> Item:
    """
    获取物品信息
    :param slug:
    :return:
    """
    url = f"{WM_API}/item/{slug}"
    response = await client.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return Item(**data.get("data", {}))

async def fetch_item_statistic(slug: str) -> ItemStatistics:
    url = f"https://api.warframe.market/v1/items/{slug}/statistics"
    response = await client.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return ItemStatistics.model_validate(data.get("payload", {}))