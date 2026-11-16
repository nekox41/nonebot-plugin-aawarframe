# Desc: 共用紫卡词条清单、二字缩写、武器限制和数值格式。
# Date: 2026-11-15
# Author: Aameow

import json
import re
from functools import lru_cache

from .resources import PACKAGED


@lru_cache(maxsize=1)
def attributes():
    data = json.loads((PACKAGED / "riven_stats.json").read_text(encoding="utf-8"))
    return {a["market_slug"]: a for a in data["attributes"]}


def normalize_attribute(value):
    return re.sub(r"[\s,，、/]+", "", value).casefold()


@lru_cache(maxsize=1)
def attribute_names():
    names = {
        normalize_attribute(name): slug
        for slug, item in attributes().items()
        for name in [item["name"], item["short"], *item.get("short_aliases", []), *item.get("name_aliases", [])]
    }
    return sorted(names.items(), key=lambda item: -len(item[0]))


def match_attributes(value):
    value = normalize_attribute(value)
    result = []
    while value:
        match = next(((name, slug) for name, slug in attribute_names() if value.startswith(name)), None)
        if match is None:
            return None
        name, slug = match
        result.append(slug)
        value = value[len(name):]
    return result


def allowed(attribute, weapon_type, positive):
    kinds = attribute["exclusive_to"]
    kind = {"archmelee": "melee"}.get(weapon_type, weapon_type)
    if kinds and kind not in kinds:
        return False
    return attribute["positive" if positive else "negative"] and not (
        not positive and kind in {"melee", "zaw"} and attribute["id"] == "Visi"
    )


def attribute_value(attribute, value, positive):
    sign = 1 if positive else -1
    if attribute["id"] == "Zeti":
        sign *= -1
    unit = attribute["unit"]
    if unit == "faction":
        return f"×{value:.2f}"
    return f"{sign * abs(value):+.1f}" + ("" if unit == "flat" else unit)
