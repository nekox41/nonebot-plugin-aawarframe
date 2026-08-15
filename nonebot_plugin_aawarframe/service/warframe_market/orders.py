from datetime import datetime, timezone
from typing import Any, Iterable, List, Dict, Optional

from jinja2 import Environment, select_autoescape
from nonebot.adapters.onebot.v11 import MessageSegment

from nonebot_plugin_htmlrender import render_html, RenderedImage
from ...integrations.warframe_market.client import fetch_orders, fetch_item, fetch_item_statistic
from ...common import read_template
from .matcher import match_slug
from ...integrations.warframe_market.schemas import Order

# Jinja2 环境（保持不变）
_JINJA_ENV = Environment(
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# 状态与平台标签（保持不变）
_STATUS_LABELS = {
    "ingame": "游戏中",
    "online": "在线",
    "offline": "离线",
    "invisible": "隐身",
}
_PLATFORM_LABELS = {
    "pc": "PC",
    "ps4": "PS",
    "ps5": "PS",
    "xboxone": "Xbox",
    "xboxsx": "Xbox",
    "switch": "Switch",
    "mobile": "Mobile",
}


# ---------- 格式化工具（保持不变） ----------
def _format_number(value: int | float) -> str:
    """格式化数字，添加千位分隔符。"""
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.1f}"
    return f"{value:,}"


def _format_price(value: float | int) -> str:
    """格式化白金价格，整数不显示小数。"""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    return str(int(value))


# ---------- 订单数据处理 ----------
def _build_order_data(order: Any, item_name: str) -> Dict[str, Any]:
    """
    将原始 Order 对象转换为模板所需的字典数据。
    所有字段在此一次性计算，避免多次遍历。
    """
    # 提取用户信息
    user = order.user
    username = user.ingameName if user and user.ingameName else "未知用户"
    status_label = _STATUS_LABELS.get(user.status, user.status) if user else "未知状态"
    platform = _PLATFORM_LABELS.get(user.platform.lower(), user.platform) if user else "未知平台"

    # 交易数量
    trade_quantity = order.perTrade if order.perTrade and order.perTrade > 0 else (order.quantity if order.quantity > 0 else 1)
    total_price = order.platinum * trade_quantity

    # 生成游戏内私聊指令（仅卖单）
    command = ""
    if order.is_sell():
        command = (
            f'/w {username} Hi! I want to buy: '
            f'x{trade_quantity} "{item_name}{'(rank '+order.rank+')' if order.rank is not None else ''}" '
            f'for {total_price} platinum. (warframe.market)'
        )

    return {
        "username": username,
        "status_label": status_label,
        "platform": platform,
        "platinum": _format_price(order.platinum),
        "trade_quantity": trade_quantity,
        "total_price": _format_price(total_price),
        "raw_platinum": order.platinum,
        "raw_trade_quantity": trade_quantity,
        "raw_total_price": total_price,
        "command": command,
    }


def _filter_visible_orders(orders: List[Any]) -> List[Any]:
    """过滤出可见且游戏内的订单。"""
    return [o for o in orders if o.visible and o.is_ingame()]


def _prepare_orders(orders: List[Any], item_name: str, order_type: str, limit: int) -> List[Dict[str, Any]]:
    """
    统一准备卖单或买单数据。
    order_type: 'sell' 或 'buy'
    卖单按价格升序，买单按价格降序，更新时间均作为次要排序（降序）。
    """
    filtered = _filter_visible_orders(orders)

    if order_type == "sell":
        target_orders = [o for o in filtered if o.is_sell()]
        target_orders.sort(key=lambda o: (o.platinum, -o.updatedAt.timestamp()))
    else:  # buy
        target_orders = [o for o in filtered if o.is_buy()]
        target_orders.sort(key=lambda o: (-o.platinum, -o.updatedAt.timestamp()))

    return [_build_order_data(o, item_name) for o in target_orders[:limit]]


# ---------- 统计数据 ----------
def _prepare_statistic_window(records: Iterable[Any]) -> Dict[str, str]:
    """
    计算一个统计时间窗口的数据（成交量与加权均价）。
    """
    records = list(records)
    total_volume = sum(max(int(r.volume), 0) for r in records)
    weighted_price_total = sum(max(int(r.volume), 0) * float(r.avg_price) for r in records)

    avg_price = weighted_price_total / total_volume if total_volume > 0 else 0.0
    return {
        "volume": _format_number(total_volume),
        "avg_price": _format_price(avg_price),
    }


def _prepare_statistics(statistics: Any) -> Dict[str, Dict[str, str]]:
    """准备 48 小时和 90 天的统计数据。"""
    return {
        "48hours": _prepare_statistic_window(statistics.forty_eight_hours),
        "90days": _prepare_statistic_window(statistics.ninety_days),
    }

# ---------- 对外接口 ----------
async def render_orders_html(user_input: str) -> str:
    """获取订单和统计数据，并渲染成 HTML。"""
    # 判断用户是否查找满级订单
    is_max = "满级" in user_input
    if is_max:
        user_input= user_input.replace("满级", "")
    # 1. 获取数据
    matched = match_slug(user_input)
    item = await fetch_item(matched)
    # 如果用户查找满级订单，但物品不存在等级
    if item.maxRank is None and is_max:
        return "此物品不存在等级"
    orders = await fetch_orders(matched)
    statistics = await fetch_item_statistic(matched)
    close_statistics = statistics.statistics_closed
    # 如果用户查找满级订单就筛选出等级等于满级的
    if is_max:
        orders = [o for o in orders if o.rank == item.maxRank]
        close_statistics.forty_eight_hours = [fe for fe in close_statistics.forty_eight_hours if fe.mod_rank == item.maxRank]
        close_statistics.ninety_days = [n for n in close_statistics.ninety_days if n.mod_rank == item.maxRank]
    if item.maxRank and not is_max:
        orders = [o for o in orders if o.rank == 0]
        close_statistics.forty_eight_hours = [fe for fe in close_statistics.forty_eight_hours if fe.mod_rank == 0]
        close_statistics.ninety_days = [n for n in close_statistics.ninety_days if n.mod_rank == 0]
    # 2. 提取物品信息
    item_name = item.i18n.get("zh-hans").name
    en_item_name = item.i18n.get("en").name


    # 3. 准备订单数据
    sell_orders = _prepare_orders(orders, en_item_name, "sell", 5)
    buy_orders = _prepare_orders(orders, en_item_name, "buy", 3)

    # 4. 准备统计数据
    statistic_data = _prepare_statistics(close_statistics)

    # 5. 准备模板上下文
    template_data = {
        "base_css": await read_template("base.css"),
        "item_name": item_name,
        "item_slug": item.slug,
        "item_tradable": item.tradable is not False,
        "item_vaulted": bool(item.vaulted),
        "item_rarity": item.rarity or "",
        "trading_tax": _format_number(item.tradingTax),
        "sell_orders": sell_orders,
        "buy_orders": buy_orders,
        "lowest_sell_price": sell_orders[0].get("platinum", "暂无"),
        "highest_buy_price": buy_orders[0].get("platinum", "暂无"),
        "command": sell_orders[0].get("command", "暂无"),
        "statistics": statistic_data,
        "updated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }

    # 6. 渲染模板
    template_text = await read_template("orders.html")
    template = _JINJA_ENV.from_string(template_text)
    return template.render(**template_data)


async def render_orders_img(user_input: str) -> RenderedImage:
    """生成物品订单图片（HTML 截图）。"""
    html = await render_orders_html(user_input)
    return await render_html(html)