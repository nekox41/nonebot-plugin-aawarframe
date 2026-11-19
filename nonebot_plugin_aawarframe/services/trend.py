# Desc: 按物品等级汇总成交量、加权均价并补齐趋势时间轴。
# Date: 2026-11-14
# Author: Aameow

from datetime import datetime, timedelta, timezone

from ..models.common import Card, DataStatus
from ..models.trend import TrendBoard, TrendPeriod, TrendPoint

SUBTYPES = {"intact": "完整", "exceptional": "优良", "flawless": "无暇", "radiant": "光辉", "blueprint": "蓝图"}


def period(rows, title, count, step, query, fetched_at):
    seconds = int(step.total_seconds())

    def bucket(time):
        return int(time.timestamp()) // seconds * seconds

    end = max((bucket(row.time) for row in rows), default=bucket(fetched_at - (step if count == 90 else timedelta())))
    start = end - (count - 1) * seconds
    sales = {}
    for row in rows:
        if query.rank is not None and row.mod_rank != query.rank:
            continue
        if query.rank is None and row.mod_rank not in {None, 0}:
            continue
        if query.subtype is not None and row.subtype != query.subtype:
            continue
        stamp = bucket(row.time)
        if start <= stamp <= end:
            volume, total, priced = sales.get(stamp, (0, 0.0, 0))
            sales[stamp] = (
                volume + row.volume,
                total + (row.price * row.volume if row.price is not None else 0),
                priced + (row.volume if row.price is not None else 0),
            )
    points = []
    for stamp in range(start, end + 1, seconds):
        volume, total, priced = sales.get(stamp, (0, 0.0, 0))
        points.append(TrendPoint(time=datetime.fromtimestamp(stamp, timezone.utc), volume=volume, price=total / priced if priced else None))
    volume = sum(point.volume for point in points)
    total = sum(value[1] for value in sales.values())
    priced = sum(value[2] for value in sales.values())
    return TrendPeriod(title=title, volume=volume, average=total / priced if priced else None, points=points)


class TrendService:
    def __init__(self, market):
        self.market = market

    async def query(self, query):
        catalog, details, query = await self.market.resolve_item(query)
        item = details.data
        if item.subtypes and query.subtype is None:
            query = query.model_copy(update={"subtype": "intact" if "intact" in item.subtypes else item.subtypes[0]})
        snapshot = await self.market.provider.statistics(item.slug)
        periods = [
            period(snapshot.data[key], title, count, step, query, snapshot.fetched_at)
            for key, title, count, step in [
                ("48hours", "48 小时", 48, timedelta(hours=1)),
                ("90days", "90 天", 90, timedelta(days=1)),
            ]
        ]
        board = TrendBoard(name=item.name(), rank=query.rank, max_rank=item.max_rank, subtype=SUBTYPES.get(query.subtype, query.subtype or ""), periods=periods)
        return Card(title=item.name() + " · 趋势", trend_board=board, source=snapshot.source, fetched_at=snapshot.fetched_at, stale=snapshot.stale or catalog.stale or details.stale, status=DataStatus.OK if any(p.volume for p in periods) else DataStatus.EMPTY)
