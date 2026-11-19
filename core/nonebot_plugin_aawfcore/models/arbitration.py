# 作用：定义仲裁当前任务与排期列表的展示数据。
# 编写日期：2026-11-14
# 作者：Aameow

from datetime import datetime

from pydantic import BaseModel, Field


class ArbitrationEntry(BaseModel):
    node_id: str
    node: str
    planet: str
    mission: str
    faction: str
    time: datetime
    remaining: str
    label: str = ""
    grade: str
    vitus_per_minute: float


class ArbitrationBoard(BaseModel):
    current: bool = False
    entries: list[ArbitrationEntry] = Field(default_factory=list)
