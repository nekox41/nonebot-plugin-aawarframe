# 作用：定位可更新的数据资源，并为整合后的 JSON 提供兼容读取。
# 编写日期：2026-11-14
# 作者：Aameow

import json
import sys
from functools import lru_cache
from pathlib import Path

PACKAGED = Path(__file__).resolve().parents[1] / "assets"


class ResourceDirectory:
    root = PACKAGED

    def __truediv__(self, name):
        return self.root / name

    def glob(self, pattern):
        return self.root.glob(pattern)


ASSETS = ResourceDirectory()
ALIASES = {
    "mission_type.json": ("descriptions.json", "mission_types"),
    "faction_type.json": ("descriptions.json", "factions"),
    "jobs.json": ("descriptions.json", "jobs"),
    "conquest_zh.json": ("descriptions.json", "text"),
}
for region in ("earth", "venus", "deimos"):
    for kind in ("tasks", "locations"):
        ALIASES[f"{region}_bounty_{kind}.json"] = ("bounties.json", region, kind)
for filename in ("drops.json", "bounty_drops.json", "challenge_bounty_drops.json"):
    ALIASES[filename] = ("rewards.json", filename)


def expand(data):
    result = dict(data)
    for name, parts in ALIASES.items():
        if name not in result and parts[0] in data:
            value = data[parts[0]]
            for part in parts[1:]:
                value = value[part]
            result[name] = value
    return result


def configure_resources(path):
    ASSETS.root = Path(path)
    raw_mapping.cache_clear()
    sources = sys.modules.get("nonebot_plugin_aawarframe.grq.sources")
    if sources:
        for name in ("catalog_seed", "item_identifiers"):
            getattr(sources, name).cache_clear()


@lru_cache(maxsize=64)
def raw_mapping(filename):
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("无效资源名称")
    path = ASSETS / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    parts = ALIASES[filename]
    value = raw_mapping(parts[0])
    for part in parts[1:]:
        value = value[part]
    return value
