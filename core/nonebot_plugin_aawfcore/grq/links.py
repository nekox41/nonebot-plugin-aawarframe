# 作用：生成并应用跨域别名投影，保留同物品和明确版本回退规则。
# 编写日期：2026-11-13
# 作者：Aameow

from collections import defaultdict

from .normalizer import normalize_name

SHARED_DOMAINS = frozenset({"Items", "Market", "Riven"})
WEAPON_CATEGORIES = {
    "Primary",
    "Secondary",
    "Melee",
    "Arch-Gun",
    "Arch-Melee",
    "SentinelWeapons",
    "Warframes",
}
PREFIXES = (
    "Kuva ",
    "Tenet ",
    "Prisma ",
    "Vaykor ",
    "Telos ",
    "Synoid ",
    "Secura ",
    "Sancti ",
    "Rakta ",
    "MK1-",
)
SUFFIXES = (" Prime", " Wraith", " Vandal", " Prisma")


def generate_links(items, market, rivens):
    by_ref = {r.identifiers.get("game.ref", r.id).casefold(): r.id for r in items.values()}
    by_name = defaultdict(set)
    for r in items.values():
        if r.metadata.get("category") in WEAPON_CATEGORIES:
            by_name[normalize_name(r.names.get("en", ""))].add(r.id)
    family = {}
    for r in items.values():
        family[r.id] = r.id
        if r.metadata.get("category") not in WEAPON_CATEGORIES:
            continue
        name = r.names.get("en", "")
        variants = [name[len(p) :] for p in PREFIXES if name.startswith(p)]
        variants += [
            name[: -len(s)]
            for s in SUFFIXES
            if name.endswith(s) and (s != " Prime" or r.metadata.get("isPrime"))
        ]
        candidates = {
            i
            for name in variants
            for i in by_name.get(normalize_name(name), ())
            if items[i].metadata.get("category") == r.metadata.get("category")
        }
        if len(candidates) == 1:
            family[r.id] = next(iter(candidates))
    records = {}

    def link(origin_domain, origin, target_domain, target, kind, priority=0):
        if origin_domain == target_domain:
            return
        key = (origin_domain, origin, target_domain, target)
        row = {
            "source_domain": origin_domain,
            "source_id": origin,
            "target_domain": target_domain,
            "target_id": target,
            "kind": kind,
            "priority": priority,
        }
        if key not in records or records[key]["priority"] > priority:
            records[key] = row

    markets_by_item = defaultdict(set)
    for m in market.values():
        ref = m.identifiers.get("game.ref", "").replace("/StoreItems/", "/").casefold()
        item_id = by_ref.get(ref)
        if not item_id:
            continue
        markets_by_item[item_id].add(m.id)
        link("Items", item_id, "Market", m.id, "same_reference")
        link("Market", m.id, "Items", item_id, "same_reference")
    for variant, base in family.items():
        if variant == base:
            continue
        for mid in markets_by_item.get(variant, ()):
            metadata = market[mid].metadata
            tags = metadata.get("tags", [])
            if "set" in tags or ("weapon" in tags and not {"blueprint", "component"} & set(tags)):
                link("Items", base, "Market", mid, "variant_fallback", 10)
    riven_for_item = {}
    for r in rivens.values():
        ref = r.identifiers.get("game.ref", "").casefold()
        item_id = by_ref.get(ref)
        if not item_id:
            ids = by_name.get(normalize_name(r.names.get("en", "")), ())
            item_id = next(iter(ids)) if len(ids) == 1 else None
        if item_id:
            riven_for_item[item_id] = r.id
            link("Riven", r.id, "Items", item_id, "riven_base")
            for item, base in family.items():
                if base == item_id:
                    link("Items", item, "Riven", r.id, "riven_compatibility")
            if family.get(item_id) != item_id:
                riven_for_item[family[item_id]] = r.id
    for row in list(records.values()):
        if row["source_domain"] == "Items" and row["target_domain"] == "Market":
            rid = riven_for_item.get(row["source_id"])
            if rid:
                link("Riven", rid, "Market", row["target_id"], row["kind"], row["priority"])
        if row["source_domain"] == "Market" and row["target_domain"] == "Items":
            rid = riven_for_item.get(family.get(row["target_id"], row["target_id"]))
            if rid:
                link("Market", row["source_id"], "Riven", rid, "riven_compatibility")
    return sorted(
        records.values(),
        key=lambda r: (
            r["source_domain"],
            r["source_id"],
            r["target_domain"],
            r["priority"],
            r["target_id"],
        ),
    )


def project_links(rows):
    targets = defaultdict(lambda: defaultdict(set))
    for row in rows:
        if not row["enabled"]:
            continue
        targets[(row["source_domain"], row["source_id"])][row["target_domain"]].add(
            (row["priority"], row["target_id"])
        )
    return {
        origin: {
            domain: frozenset(
                target for priority, target in options if priority == min(p for p, _ in options)
            )
            for domain, options in domains.items()
        }
        for origin, domains in targets.items()
    }
