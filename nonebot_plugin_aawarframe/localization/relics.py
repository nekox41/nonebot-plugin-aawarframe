# Desc: 从 GRQ 现有物品生成遗物奖励、部件反查和配方关联索引。
# Date: 2026-11-15
# Author: Aameow

import re
from collections import defaultdict
from threading import RLock

from ..grq import get_grq
from ..grq.normalizer import normalize_name, normalize_ref
from ..models.errors import UserInputError
from ..models.relics import RelicReference, RelicReward

ERAS = {"Lith": "古纪", "Meso": "前纪", "Neo": "中纪", "Axi": "后纪", "Vanguard": "先锋", "Requiem": "安魂"}
QUALITIES = ("Intact", "Exceptional", "Flawless", "Radiant")
RELIC_NAME = re.compile(rf"({'|'.join(ERAS)}) (.+) ({'|'.join((*QUALITIES, 'Relic'))})")


def prime_name(value):
    return re.sub(r"(?<=[\u4e00-\u9fff\s])[pP](?=\s|$)", " Prime", value.strip())


class RelicIndex:
    def __init__(self):
        self.lock = RLock()
        self.version = -1

    def prepare(self):
        grq = get_grq()
        with self.lock, grq.lock:
            if self.version == grq.version:
                return
            self.relics, self.names, self.reverse, self.aliases = {}, {}, defaultdict(dict), {}
            self.parts, self.parents, self.reward_items = set(), set(), {}
            for item in grq.domains["Items"].resources.values():
                if not item.enabled or item.metadata.get("category") != "Relics":
                    continue
                resource = grq.get("Items", item.id)
                data = resource.metadata
                match = RELIC_NAME.fullmatch(resource.names.get("en", ""))
                if not match or not data.get("rewards"):
                    continue
                era, code, quality = match.groups()
                quality = "Intact" if quality == "Relic" else quality
                key = normalize_name(era + code)
                relic = self.relics.setdefault(key, {"name": ERAS[era] + " " + code, "era": list(ERAS).index(era), "code": code, "vaulted": bool(data.get("vaulted")), "qualities": {}})
                relic["qualities"][quality] = data["rewards"]
                for name in [era + code, ERAS[era] + code, *resource.names.values(), *resource.aliases]:
                    name = re.sub(r"(?i)\b(Intact|Exceptional|Flawless|Radiant|Relic)\b|遗物|完整|优良|无暇|光辉", "", name)
                    self.names[normalize_name(name)] = key
            for key, relic in self.relics.items():
                for reward in relic["qualities"]["Intact"]:
                    raw = reward["item"]["uniqueName"]
                    ref = normalize_ref(raw)
                    self.reward_items[ref] = reward["item"]
                    chance = reward["chance"]
                    rarity = {2: "rare", 11: "uncommon", 25.33: "common"}.get(chance, reward.get("rarity", "Common").lower())
                    self.reverse[ref][key] = RelicReference(name=relic["name"], rarity=rarity, vaulted=relic["vaulted"])
                    resource = grq.get("Items", raw, "game.ref")
                    if resource:
                        self.parts.add(resource.id)
                        self.parents.update(resource.metadata.get("parentUniqueNames", []))
                    if raw.endswith("Blueprint"):
                        component = grq.get("Items", raw[:-9] + "Component", "game.ref")
                        if component:
                            self.aliases[normalize_ref(component.id)] = ref
                            self.parts.add(component.id)
                            self.parents.update(component.metadata.get("parentUniqueNames", []))
            self.parents = {r.id for ref in self.parents if (r := grq.get("Items", ref, "game.ref"))}
            for parent in self.parents:
                for component in grq.get("Items", parent).metadata.get("components", []):
                    child = grq.get("Items", component["uniqueName"], "game.ref")
                    if child and child.metadata.get("category") == "Components":
                        self.parts.add(child.id)
            self.version = grq.version

    def canonical(self, ref):
        key = normalize_ref(ref)
        return self.aliases.get(key, key)

    def relic(self, query):
        key = normalize_name(re.sub(r"遗物|完整|优良|无暇|光辉", "", query))
        if key not in self.names:
            raise UserInputError("未找到遗物，例如：遗物 古纪A1。")
        return self.relics[self.names[key]]

    def item(self, query):
        grq = get_grq()
        result = grq.search("Items", prime_name(query), self.parts | self.parents)
        if not result.resource:
            market = grq.search_market(prime_name(query))
            if market.resource and market.resource.id in self.parents:
                return grq.get("Items", market.resource.id)
        if result.status == "ambiguous" and len(result.candidates) > 1:
            raise UserInputError("名称不够明确：" + "、".join(r.name() for r in result.candidates))
        if not result.candidates:
            raise UserInputError("未找到有遗物掉落的物品，请使用完整名称，例如：部件 阿利乌双枪p 枪机。")
        return grq.get("Items", result.candidates[0].id)

    def rewards(self, relic):
        grq = get_grq()
        rewards = {}
        for quality, rows in relic["qualities"].items():
            for row in rows:
                item = row["item"]
                quantity = re.match(r"(\d+)\s*[xX]\s+", item["name"])
                quantity = int(quantity[1]) if quantity else 1
                key = (normalize_ref(item["uniqueName"]), quantity)
                if key not in rewards:
                    resource = grq.get("Items", item["uniqueName"], "game.ref")
                    slug = resource.identifiers.get("market.slug", "") if resource else ""
                    slug = slug or item.get("warframeMarket", {}).get("urlName", "")
                    rewards[key] = RelicReward(ref=item["uniqueName"], name=resource.name() if resource else item["name"], slug=slug, quantity=quantity, chances=[None] * 4)
                rewards[key].chances[QUALITIES.index(quality)] = row["chance"]
        return sorted(rewards.values(), key=lambda row: -(row.chances[0] or 0))
