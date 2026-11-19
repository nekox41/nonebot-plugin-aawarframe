# 作用：统一奖励表结构，校验概率，并为原赏金查询生成兼容视图。
# 编写日期：2026-11-13
# 作者：Aameow

from math import isfinite

STAGE_LABELS = ("阶段 1", "中间阶段", "五阶段赏金的阶段 4", "最终阶段")


def from_pools(pools):
    rotations = []
    for index, pool in enumerate(pools):
        rewards = []
        for entry in pool:
            rewards.append(
                {
                    "item_id": entry.get("type"),
                    "name": entry["name"],
                    "quantity": entry.get("itemCount", 1),
                    "probability": entry["probability"],
                }
            )
        rotations.append(
            {
                "id": str(index),
                "label": STAGE_LABELS[index] if len(pools) == 4 else "完成奖励",
                "rewards": rewards,
            }
        )
    return rotations


def to_pools(rotations):
    return [
        [
            {
                "type": r.get("item_id") or r.get("name_en") or r["name"],
                "name": r["name"],
                "itemCount": r.get("quantity", 1),
                "probability": r["probability"],
            }
            for r in block["rewards"]
        ]
        for block in rotations
    ]


def validate_table(metadata):
    rotations = metadata.get("rotations")
    if not isinstance(rotations, list) or not rotations:
        raise ValueError("奖励表必须包含奖励池和具体奖励列表")
    for block in rotations:
        if (
            not isinstance(block, dict)
            or not isinstance(block.get("rewards"), list)
            or not block["rewards"]
        ):
            raise ValueError("每个奖励池必须包含奖励列表")
        for entry in block["rewards"]:
            if not entry.get("name"):
                raise ValueError("奖励名称不能为空")
            chance = entry.get("probability")
            if chance is not None and (
                isinstance(chance, bool)
                or not isinstance(chance, (int, float))
                or not isfinite(chance)
                or not 0 <= chance <= 1
            ):
                raise ValueError("奖励概率须为 0 到 1 之间的数值")
            if not isinstance(entry.get("quantity", 1), int) or entry.get("quantity", 1) <= 0:
                raise ValueError("奖励数量必须为正整数")
    return metadata
