# Desc: 按最接近的武器家族计算满级紫卡普通与融合词条范围。
# Date: 2026-11-14
# Author: Aameow

import json
from struct import pack, unpack

from ..grq import get_grq
from ..grq.links import PREFIXES, SUFFIXES
from ..localization.resources import PACKAGED
from ..models.common import Card
from ..models.errors import UserInputError
from ..models.riven_values import RivenAttribute, RivenValuesBoard, RivenVariant

CLASS_NAMES = {"rifle": "步枪", "shotgun": "霰弹枪", "pistol": "手枪", "archgun": "Arch 枪械", "melee": "近战"}
VINTAGE = {"Hera", "Zeti", "Ampi", "Tempi", "Pleci", "Exi", "Forti", "Para", "GainCombo"}
PHYSICAL = {"Magna": "impact", "Insi": "puncture", "Sci": "slash"}
VARIANT_BASES = {"Dex Furis": "Afuris", "Dex Sybaris": "Sybaris"}


def family_names(name):
    if name in VARIANT_BASES:
        return {VARIANT_BASES[name]}
    return {
        name,
        *(name[len(p):] for p in (*PREFIXES, "Mara ", "Coda ", "Carmine ") if name.startswith(p)),
        *(name[:-len(s)] for s in SUFFIXES if name.endswith(s)),
    }


def f32(value):
    return unpack("f", pack("f", value))[0]


def value_range(attribute, weapon_class, multiplier, disposition):
    if not multiplier:
        return "—"
    values = []
    for quality in (0.9, 1.1):
        value = f32(attribute["coefficients"][weapon_class])
        for factor in (10, 9, disposition, multiplier, quality):
            value = f32(value * f32(factor))
        unit = attribute["unit"]
        if unit == "%":
            value = f32(value * (-100 if attribute["inverse"] else 100))
        elif unit == "faction":
            value = f32(1 + value)
        values.append(value)
    low, high = sorted(values)
    if unit == "faction":
        return f"×{low:.2f}～×{high:.2f}"
    suffix = "" if unit == "flat" else unit
    return f"{low:+.1f}～{high:+.1f}{suffix}"


class RivenValuesService:
    def __init__(self):
        self.rules = json.loads((PACKAGED / "riven_stats.json").read_text(encoding="utf-8"))
        self._version = -1
        self._families = {}

    def family(self, riven):
        grq = get_grq()
        if self._version != grq.version:
            self._families = {}
            for row in grq.links:
                if row["source_domain"] == "Items" and row["target_domain"] == "Riven":
                    self._families.setdefault(row["target_id"], set()).add(row["source_id"])
            self._version = grq.version
        ids = set(self._families.get(riven.id, ()))
        base = grq.get("Items", riven.identifiers.get("game.ref", ""), "game.ref")
        if base:
            ids.add(base.id)
            # 补充旧快照尚未建立兼容链接的版本，排除蓝图、零件和市场套装。
            names = family_names(riven.names.get("en", ""))
            for item in grq.domains["Items"].resources.values():
                if item.metadata.get("category") == base.metadata.get("category") and names & family_names(item.names.get("en", "")):
                    ids.add(item.id)
        weapons = [grq.get("Items", key) for key in ids]
        owned = {
            r.identifiers.get("game.ref"): r.id
            for r in grq.domains["Riven"].resources.values()
        }
        weapons = [
            w for w in weapons
            if w and w.enabled and "omegaAttenuation" in w.metadata
            and owned.get(w.identifiers.get("game.ref"), riven.id) == riven.id
        ]
        return sorted(weapons, key=lambda w: (w.id != (base.id if base else ""), w.names.get("en", "")))

    def attributes(self, weapon, riven, family, layout, weapon_class):
        metadata = weapon.metadata
        companion = metadata.get("sentinel") or metadata.get("productCategory") == "SentinelWeapons" or riven.metadata.get("group") == "sentinel"
        ordinary = [a for a in self.rules["attributes"] if not a["spliced"] and a["coefficients"].get(weapon_class) is not None and not (companion and a["id"] in VINTAGE)]
        # 物理词条按整个家族的原始攻击伤害筛选；灵化形态不改变同张紫卡的词条池。
        physical = set()
        for variant in family:
            damage = variant.metadata.get("damage", {})
            total = variant.metadata.get("totalDamage") or damage.get("total", 0)
            physical.update(key for key, kind in PHYSICAL.items() if total and damage.get(kind, 0) / total > 0.25)
        ordinary = [a for a in ordinary if a["id"] not in PHYSICAL or a["id"] in physical]
        ids = {a["id"] for a in ordinary}
        spliced = [a for a in self.rules["attributes"] if a["spliced"] and a["coefficients"].get(weapon_class) is not None and any(set(pair) <= ids for pair in a["requires"])]
        bonus, malus = self.rules["layouts"][layout]

        def row(a):
            name = a["name"]
            if weapon_class == "melee" and a["id"] == "Croni":
                name = "攻击速度"
            if weapon_class == "melee" and a["id"] == "Crita":
                name = "暴击几率（重击×2）"
            if a["id"] == "Croni" and metadata.get("type") == "Bow":
                name = "射速（弓类×2）"
            positive = value_range(a, weapon_class, bonus, self.rules["disposition"]) if a["positive"] else "—"
            negative_allowed = a["negative"] and not (weapon_class == "melee" and a["id"] == "Visi")
            negative = value_range(a, weapon_class, malus, self.rules["disposition"]) if negative_allowed else "—"
            return RivenAttribute(name=name, positive=positive, negative=negative)

        return [row(a) for a in ordinary], [row(a) for a in spliced]

    def query(self, query, layout="3+1"):
        if layout not in self.rules["layouts"]:
            raise UserInputError("词条修正支持 2+0、2+1、3+0、3+1。")
        grq = get_grq()
        result = grq.search("Riven", query)
        if not result.candidates and query.lower().endswith("p"):
            result = grq.search("Riven", query[:-1].strip() + " Prime")
        if not result.candidates:
            raise UserInputError("未找到对应的紫卡武器，请使用完整武器名称。")
        riven = result.candidates[0]
        weapons = self.family(riven)
        if not weapons:
            raise UserInputError("该武器暂缺完整资料，请更新物品资源后重试。")
        weapon_class = riven.metadata.get("weapon_type")
        if weapon_class not in CLASS_NAMES:
            weapon_class = riven.metadata.get("rivenType")
        weapon_class = {"kitgun": "pistol", "zaw": "melee"}.get(weapon_class, weapon_class)
        if weapon_class not in CLASS_NAMES:
            raise UserInputError("暂不支持该武器的紫卡类型。")
        variants = []
        for weapon in weapons:
            ordinary, spliced = self.attributes(weapon, riven, weapons, layout, weapon_class)
            variants.append(RivenVariant(name=weapon.name(), weapon_class=CLASS_NAMES[weapon_class], ordinary=ordinary, spliced=spliced))
        return Card(title="紫卡数值 · " + riven.name(), source=self.rules["source"], riven_values_board=RivenValuesBoard(layout=layout, variants=variants))
