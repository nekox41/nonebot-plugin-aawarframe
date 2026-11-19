# Desc: 通过 GRQ 共用紫卡武器名称、别名和模糊匹配。
# Date: 2026-11-14
# Author: Aameow

from ..grq import get_grq
from ..models.errors import UserInputError

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


def riven_type_name(item_type: str) -> str:
    return RIVEN_TYPES.get(item_type, item_type)


def riven_name(compatibility: str | None, item_type: str) -> str:
    if not compatibility:
        return riven_type_name(item_type) + "（未指定武器）"
    resource = get_grq().get("Riven", compatibility, "riven.compatibility")
    return resource.name() if resource else compatibility


def resolve_riven_weapon(query: str):
    grq = get_grq()
    result = grq.search("Riven", query)
    if not result.candidates and query.lower().endswith("p"):
        result = grq.search("Riven", query[:-1].strip() + " Prime")
    if not result.candidates:
        raise UserInputError("未找到对应的紫卡武器，请使用完整武器名称。")
    return result.candidates[0]


def resolve_riven_names(query: str, available: set[str]) -> list[str]:
    grq = get_grq()
    grq.ensure_rivens(available)
    allowed = {grq.get("Riven", v, "riven.compatibility").id for v in available}
    result = grq.search("Riven", query, allowed)
    if result.resource:
        return [result.resource.identifiers["riven.compatibility"]]
    if result.status == "ambiguous":
        raise UserInputError(
            "名称不够明确，请使用完整名称：" + "、".join(r.name() for r in result.candidates)
        )
    return []
