import json
from typing import List

from pydantic import BaseModel
from ...common import TEMPLATES_DIR, ASSETS_DIR
from ...integrations.world_state import fetch_world_state
from nonebot_plugin_htmlrender import render_template


class Reward(BaseModel):
    name: str
    probability: float
    item_count: int
    stage: str

    def __str__(self):
        return f"{self.item_count}x {self.name} {self.probability * 100:.2f}%"


class Bounty(BaseModel):
    min_level: int
    max_level: int
    rewards: List[Reward]
    title: str
    desc: str

    def __str__(self):
        rewards_str = "\n".join(str(r) for r in self.rewards)
        return f"{self.title} 等级：{self.min_level} - {self.max_level}\n{self.desc}\n----\n{rewards_str}"


# 通过敌人的最高等级，判断总共有几阶段任务，每阶段任务使用哪个掉落表
STAGE_MAP = {
    15: [0, 1, -1],
    30: [0, 1, -1],
    40: [0, 1, 1, -1],
    50: [0, 1, 1, 2, -1],
    60: [0, 1, 1, 2, -1],
    100: [0, 1, 1, 2, -1],
    70: [0, 1, 1, 2, -1],
}


async def gen_cetus_bounty_img():
    world_state = await fetch_world_state()
    cetus_bounty = None
    for s in world_state.SyndicateMissions:
        if s.Tag == "CetusSyndicate" and s.is_valid():
            cetus_bounty = s
    jobs = cetus_bounty.Jobs

    # 读取 Jobs
    with open(ASSETS_DIR / "jobs.json", "r", encoding="utf-8") as f:
        jobs_map = json.load(f)
    # 读取 Drops
    with open(ASSETS_DIR / "drops.json", "r", encoding="utf-8") as f:
        drops_map = json.load(f)
    all_bounty = []
    for job in jobs:
        # 获取敌人最高等级
        max_level = job.maxEnemyLevel
        # 获取 Stage
        stage = STAGE_MAP[max_level]
        stage_len = len(stage)
        # 获取具体掉落表
        drop_table = drops_map[job.rewards]
        # 获取每个 Stage 的具体掉落表
        rewards = []
        for i, value in enumerate(stage):
            items = drop_table[value]
            i += 1
            if i == 1:
                current_stage = "阶段一"
            if i == 2:
                current_stage = "阶段二"
            if i == 3:
                current_stage = "阶段三"
            if i == 4:
                current_stage = "阶段四"
            if i == 5:
                current_stage = "阶段五"

            # 将每个奖励物品映射为 Reward
            for item in items:
                rewards.append(
                    Reward(
                        name=item["name"],
                        probability=item["probability"],
                        item_count=item["itemCount"],
                        stage=current_stage,
                    )
                )

        title = jobs_map[job.jobType.split("/")[-1] + "Title"]
        if max_level == 100:
            title += "（钢铁）"
        all_bounty.append(
            Bounty(
                title=title,
                desc=jobs_map[job.jobType.split("/")[-1] + "Desc"],
                min_level=job.minEnemyLevel,
                max_level=job.maxEnemyLevel,
                rewards=rewards,
            )
        )

    stage_order = [15, 30, 40, 50, 60, 100, 70]
    all_bounty.sort(key=lambda bounty: stage_order.index(bounty.max_level))

    return await render_template(
        TEMPLATES_DIR, "bouties.html", {"bounties": all_bounty}
    )
