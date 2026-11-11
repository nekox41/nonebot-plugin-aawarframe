# 作用：定义赏金任务、阶段掉落及卡片展示数据。
# 编写日期：2026-11-07
# 作者：Aameow

from pydantic import BaseModel, Field, FiniteFloat


class StageReward(BaseModel):
    item_type: str = Field(alias="type", min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(alias="itemCount", ge=1)
    probability: FiniteFloat = Field(ge=0, le=1)


class BountyReward(BaseModel):
    name: str
    quantity: int
    chances: list[float | None]


class BountyDisplay(BaseModel):
    index: int
    name: str
    kind: str
    min_level: int
    max_level: int
    stages: int
    standing: int | None
    mastery: int | None
    rotation: str
    rewards: list[BountyReward] = Field(default_factory=list)
    message: str = ""
    task_pools: list[list[str]] = Field(default_factory=list)
    task_pool_note: str = ""
    reward_labels: list[str] = Field(default_factory=lambda: [f"阶段 {i}" for i in range(1, 6)])
    reward_caption: str = "五阶段单次奖励概率参考；不含额外奖励次数。"
    task_pool_title: str = "五阶段可能任务池"
    node: str = ""
    mission: str = ""
    faction: str = ""
    objectives: list[str] = Field(default_factory=list)
    ally: str = ""
    chemistry: int = 0
