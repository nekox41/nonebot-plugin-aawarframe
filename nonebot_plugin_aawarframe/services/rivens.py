# 作用：实现 services 层的 rivens 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
from math import ceil
from typing import Literal

from ..localization.rivens import resolve_riven_names, riven_name
from ..models.common import Card, DataStatus, Section
from ..models.errors import UserInputError
from ..models.rivens import RivenSnapshot
from ..providers.rivens import RivenProvider

PAGE_SIZE = 10
MIN_POPULARITY = 5


def price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def data_notes(snapshot: RivenSnapshot) -> list[str]:
    notes = [
        "PC 官方周成交统计，价格单位：白金。",
        "热度为相对值（最高 100），不是成交笔数。",
        "每日同步一次，源数据按周更新；历史统计不代表某张紫卡的当前报价。",
    ]
    if snapshot.source_updated_at:
        notes.append(f"官方文件更新：{snapshot.source_updated_at:%Y-%m-%d %H:%M} UTC")
    if snapshot.skipped_records:
        notes.append(f"已跳过 {snapshot.skipped_records} 条格式异常的记录。")
    return notes


class RivenService:
    def __init__(self, provider: RivenProvider):
        self.provider = provider

    async def ranking(
        self,
        page: int = 1,
        sort_by: Literal["median", "popularity"] = "median",
        *,
        rerolled: bool = False,
    ) -> Card:
        command = "已洗紫卡排行" if rerolled else "紫卡排行"
        state = "已洗" if rerolled else "未洗"
        if page < 1:
            raise UserInputError(f"页码必须是正整数，例如：{command}2。")
        if sort_by not in {"median", "popularity"}:
            raise UserInputError(f"排序只支持中位价或热度，例如：{command}3 热度。")
        snapshot = await self.provider.fetch()

        def sort_key(record):
            median = record.median if record.median is not None else -1
            first, second = (
                (median, record.popularity) if sort_by == "median" else (record.popularity, median)
            )
            return (-first, -second, record.compatibility or "", record.item_type)

        records = sorted(
            [
                record
                for record in snapshot.data
                if record.rerolled == rerolled and record.popularity >= MIN_POPULARITY
            ],
            key=sort_key,
        )
        total = max(1, ceil(len(records) / PAGE_SIZE))
        if page > total:
            raise UserInputError(
                f"{command}共有 {total} 页，请输入 1–{total}，例如：{command}3 热度。"
            )
        start = (page - 1) * PAGE_SIZE
        section = Section(
            title=f"{state}紫卡：第 {page} / {total} 页，共 {len(records)} 条，每页 10 条",
            columns=["排名", "武器", "中位价", "均价", "热度"],
        )
        for rank, record in enumerate(records[start : start + PAGE_SIZE], start + 1):
            section.rows.append(
                [
                    str(rank),
                    f"{riven_name(record.compatibility, record.item_type)}（{state}）",
                    price(record.median),
                    price(record.average),
                    f"{record.popularity:g}",
                ]
            )
        notes = data_notes(snapshot)
        notes.append("仅展示热度 ≥ 5 的记录。")
        notes.insert(
            0,
            "按中位价降序排列。" if sort_by == "median" else "按热度降序排列，同热度按中位价降序。",
        )
        notes.append(f"本榜只包含{state}记录；中位价缺失时不以均价代替，排在同排序组末尾。")
        if not records:
            notes.append(f"本周暂无可用的{state}紫卡交易记录。")
        title = f"{state}紫卡中位价排行" if sort_by == "median" else f"{state}紫卡热度排行"
        return Card(
            title=title,
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
            stale=snapshot.stale,
            status=DataStatus.OK if records else DataStatus.EMPTY,
            sections=[section],
            notes=notes,
            page_number=page,
            total_pages=total,
        )

    async def statistics(self, query: str) -> Card:
        snapshot = await self.provider.fetch()
        available = {record.compatibility for record in snapshot.data if record.compatibility}
        matches = await asyncio.to_thread(resolve_riven_names, query, available)
        notes = data_notes(snapshot)
        if not matches:
            notes.insert(0, f"未找到“{query}”的本周紫卡统计，请检查武器名称或使用英文名称。")
            return Card(
                title="紫卡周统计",
                source=snapshot.source,
                fetched_at=snapshot.fetched_at,
                stale=snapshot.stale,
                status=DataStatus.EMPTY,
                notes=notes,
            )
        if len(matches) > 1:
            options = "、".join(riven_name(name, "") for name in matches[:10])
            raise UserInputError(f"匹配到多个武器：{options}。请使用完整名称查询。")
        weapon = matches[0]
        records = sorted(
            [record for record in snapshot.data if record.compatibility == weapon],
            key=lambda record: (record.rerolled, record.item_type),
        )
        section = Section(
            title="已洗 / 未洗周统计", columns=["武器", "中位价", "均价", "标准差", "热度"]
        )
        for record in records:
            section.rows.append(
                [
                    riven_name(weapon, record.item_type)
                    + ("（已洗）" if record.rerolled else "（未洗）"),
                    price(record.median),
                    price(record.average),
                    price(record.standard_deviation),
                    f"{record.popularity:g}",
                ]
            )
        for rerolled, label in [(False, "未洗"), (True, "已洗")]:
            if not any(record.rerolled == rerolled for record in records):
                section.notes.append(f"本周没有该武器的{label}统计记录。")
        name = riven_name(weapon, "")
        notes.insert(0, f"查询：{query}；匹配武器：{name}（{weapon}）。")
        return Card(
            title=f"紫卡周统计：{name}",
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
            stale=snapshot.stale,
            status=DataStatus.OK if records else DataStatus.EMPTY,
            sections=[section],
            notes=notes,
        )
