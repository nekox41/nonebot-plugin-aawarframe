# 作用：校验并合并地球赏金各阶段的奖励概率。
# 编写日期：2026-11-07
# 作者：Aameow

from ...models.bounties import BountyReward, StageReward
from .common import ParseError

# DE 掉落表依次为首阶段、中间阶段、五阶段任务的第四阶段、最终阶段。
STAGE_POOLS = {3: [0, 1, 3], 4: [0, 1, 1, 3], 5: [0, 1, 1, 2, 3]}


def parse_rewards(pools: list, count: int) -> list[BountyReward]:
    if count not in STAGE_POOLS or not isinstance(pools, list) or len(pools) != 4:
        raise ParseError("赏金阶段或掉落表格式尚未支持")
    return merge_reward_pools(pools, STAGE_POOLS[count])


def merge_reward_pools(pools: list, indices: list[int]) -> list[BountyReward]:
    """合并选定的奖励池，普通阶段和隔离库完成奖励共用校验。"""
    rows: dict[tuple[str, int], BountyReward] = {}
    try:
        for stage, pool in enumerate(indices):
            if not isinstance(pools[pool], list) or not pools[pool]:
                raise ParseError("阶段奖励为空")
            for entry in pools[pool]:
                reward = StageReward.model_validate(entry)
                key = reward.item_type, reward.quantity
                row = rows.setdefault(
                    key,
                    BountyReward(
                        name=reward.name, quantity=reward.quantity, chances=[None] * len(indices)
                    ),
                )
                row.chances[stage] = (row.chances[stage] or 0) + reward.probability
                if row.chances[stage] > 1.0001:
                    raise ParseError("阶段奖励概率超出范围")
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ParseError("阶段奖励格式无效") from exc
    return list(rows.values())
