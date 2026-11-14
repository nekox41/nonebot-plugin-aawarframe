# 作用：依据赏金种子计算各平原的图内据点任务。
# 编写日期：2026-11-07
# 作者：Aameow

from ...localization.resolver import load_mapping
from ..seeded_random import SeededRandom


def location_bounties(seed: int, region: str = "earth") -> dict[str, list[str]]:
    """按地点配置顺序共享随机序列；算法参考 wf.browse.oracle/location-bounties.pluto。"""
    locations = load_mapping(f"{region}_bounty_locations.json")["locations"]
    result = {}
    random = SeededRandom(seed)
    for location in locations:
        selected = [i < location["NumJobsToShow"] for i in range(len(location["Jobs"]))]
        random.shuffle(selected)
        label = location.get("label", "帐篷 " + location["LocationTag"].removeprefix("Tent"))
        result[label] = [job["name"] for job, enabled in zip(location["Jobs"], selected) if enabled]
    return result
