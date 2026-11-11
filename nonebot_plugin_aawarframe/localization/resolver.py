# 作用：实现 localization 层的 resolver 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import json
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

ASSETS = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=16)
def load_mapping(filename: str) -> dict:
    return json.loads((ASSETS / filename).read_text(encoding="utf-8"))


def translate(value: str) -> str:
    for filename in ("conquest_zh.json", "mission_type.json", "faction_type.json", "jobs.json"):
        mapping = load_mapping(filename)
        if value in mapping:
            return str(mapping[value])
    # 未知标识保留原值，不推测翻译。
    return value


def node_info(value: str) -> dict:
    return load_mapping("ExportRegions_zh.json").get(value, {"name": value})


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


class ItemResolver:
    def __init__(self, items: list):
        allowed = {item.slug for item in items}
        self.names = {
            normalize(name): slug
            for name, slug in load_mapping("wm_pitems.json").items()
            if slug in allowed
        }
        for item in items:
            self.names[normalize(item.slug)] = item.slug
            for locale in item.i18n.values():
                self.names[normalize(locale.name)] = item.slug

    def resolve(self, value: str) -> str | None:
        cleaned = normalize(value)
        if not cleaned:
            return None
        if cleaned in self.names:
            return self.names[cleaned]
        match = process.extractOne(
            cleaned,
            sorted(self.names),
            scorer=Levenshtein.distance,
            score_cutoff=max(1, len(cleaned) // 3),
        )
        return self.names[match[0]] if match else None
