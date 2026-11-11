# 作用：实现 localization 层的 rivens 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import re
from functools import lru_cache

from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

from .resolver import load_mapping, normalize

RIVEN_TYPES = {
    "Archgun Riven Mod": "重型武器紫卡",
    "Kitgun Riven Mod": "组合枪紫卡",
    "Melee Riven Mod": "近战紫卡",
    "Pistol Riven Mod": "手枪紫卡",
    "Rifle Riven Mod": "步枪紫卡",
    "Shotgun Riven Mod": "霰弹枪紫卡",
    "Companion Weapon Riven Mod": "同伴武器紫卡",
    "Sentinel Weapon Riven Mod": "守护武器紫卡",
    "Zaw Riven Mod": "Zaw 紫卡",
}


@lru_cache(maxsize=1)
def _weapon_names() -> dict[str, str]:
    aliases = load_mapping("wm_pitems.json")
    chinese = {}
    for name, slug in aliases.items():
        if re.search(r"[\u4e00-\u9fff]", name):
            chinese.setdefault(slug, name)
    names = {
        normalize(name): chinese[slug]
        for name, slug in aliases.items()
        if name.isascii() and slug in chinese
    }
    # 专门的紫卡武器目录优先，避免普通交易目录缺失基础武器或选中不规范别名。
    names.update(
        {
            normalize(english): chinese
            for english, chinese in load_mapping("riven_weapons.json").items()
        }
    )
    return names


def riven_type_name(item_type: str) -> str:
    return RIVEN_TYPES.get(item_type, item_type)


def riven_name(compatibility: str | None, item_type: str) -> str:
    if not compatibility:
        return riven_type_name(item_type) + "（未指定武器）"
    return _weapon_names().get(normalize(compatibility), compatibility)


def resolve_riven_names(query: str, available: set[str]) -> list[str]:
    aliases: dict[str, set[str]] = {}
    normalized: dict[str, set[str]] = {}
    for weapon in sorted(available):
        normalized.setdefault(normalize(weapon), set()).add(weapon)
        for name in [weapon, riven_name(weapon, "")]:
            aliases.setdefault(normalize(name), set()).add(weapon)
    for alias, slug in load_mapping("wm_pitems.json").items():
        if normalize(slug) in normalized:
            aliases.setdefault(normalize(alias), set()).update(normalized[normalize(slug)])
    key = normalize(query)
    if not key:
        return []
    if key in aliases:
        return sorted(aliases[key])
    cutoff = min(2, len(key) // 3)
    matches = process.extract(
        key, sorted(aliases), scorer=Levenshtein.distance, score_cutoff=cutoff, limit=None
    )
    if not matches:
        return []
    closest = min(match[1] for match in matches)
    return sorted(
        {
            weapon
            for alias, distance, _ in matches
            if distance == closest
            for weapon in aliases[alias]
        }
    )
