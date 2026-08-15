from ...integrations.warframe_market.schemas import Order
from typing import List

def sort_and_filter_orders(orders: List[Order]) -> List[Order]:
    """
    筛选出所有 ingame 状态订单，随后按照金额从小到大排序，同金额的按照 updateAt 排序。
    :param orders:
    :return:
    """
    ingame_orders = [o for o in orders if o.is_ingame()]
    ingame_orders.sort(key=lambda o: (o.platinum, -o.updatedAt.timestamp()))
    return ingame_orders