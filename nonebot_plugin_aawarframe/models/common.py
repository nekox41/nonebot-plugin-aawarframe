from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    PARSE_ERROR = "parse_error"
    UNAVAILABLE = "unavailable"


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: Any
    source: str
    fetched_at: datetime = Field(default_factory=utcnow)
    stale: bool = False


class Section(BaseModel):
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Card(BaseModel):
    title: str
    source: str
    fetched_at: datetime = Field(default_factory=utcnow)
    status: DataStatus = DataStatus.OK
    stale: bool = False
    sections: list[Section] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    page_number: int | None = Field(default=None, ge=1)
    total_pages: int | None = Field(default=None, ge=1)

    def text(self) -> str:
        lines = [self.title]
        if self.stale:
            lines.append("【过期缓存】上游暂不可用，请留意数据时间。")
        lines.extend(self.notes)
        for section in self.sections:
            lines.append(section.title)
            if section.columns:
                lines.append(" | ".join(section.columns))
            lines.extend(" | ".join(row) for row in section.rows)
            lines.extend(section.notes)
        lines.append(f"来源：{self.source}")
        lines.append(f"获取时间：{self.fetched_at:%Y-%m-%d %H:%M:%S} UTC")
        return "\n".join(lines)
