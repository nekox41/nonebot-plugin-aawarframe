# 作用：实现 models 层的 rivens 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import logging
from datetime import datetime

import json5
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool

from .common import Snapshot

logger = logging.getLogger(__name__)


class RivenRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item_type: str = Field(alias="itemType", min_length=1)
    compatibility: str | None = None
    rerolled: StrictBool
    average: FiniteFloat = Field(alias="avg", ge=0)
    median: FiniteFloat | None = Field(default=None, ge=0)
    minimum: FiniteFloat = Field(alias="min", ge=0)
    maximum: FiniteFloat = Field(alias="max", ge=0)
    popularity: FiniteFloat = Field(alias="pop", ge=0)
    standard_deviation: FiniteFloat | None = Field(default=None, alias="stddev", ge=0)


class RivenSnapshot(Snapshot):
    data: list[RivenRecord]
    source_updated_at: datetime | None = None
    skipped_records: int = 0


def parse_riven_records(text: str) -> tuple[list[RivenRecord], int]:
    # 官方文件可能使用单引号和未加引号的键，使用 JSON5 解析，绝不执行脚本。
    raw = json5.loads(text, allow_duplicate_keys=False)
    if not isinstance(raw, list):
        raise ValueError("官方紫卡数据不是列表")
    records = []
    skipped = 0
    for index, item in enumerate(raw):
        try:
            records.append(RivenRecord.model_validate(item))
        except (ValueError, TypeError):
            skipped += 1
            logger.warning("官方紫卡记录 %s 解析失败，已跳过", index)
    if raw and not records:
        raise ValueError("官方紫卡记录全部解析失败")
    return records, skipped
