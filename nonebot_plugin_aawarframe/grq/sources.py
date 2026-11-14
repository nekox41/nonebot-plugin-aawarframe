# 作用：预处理物品、任务池和奖励表，生成七个域的完整资料。
# 编写日期：2026-11-13
# 作者：Aameow

import gzip
import json
from functools import lru_cache

from ..localization.resources import ASSETS
from .models import Resource
from .normalizer import normalize_name
from .registry import DESC_FILES, DOMAIN_NAMES, DROP_FILES, file_domain, mapped_id, misc_id
from .rewards import from_pools


@lru_cache(maxsize=1)
def catalog_seed():
    path = ASSETS / "grq/items.json.gz"
    if not path.exists():
        raise ValueError("缺少预处理的 WFCD 物品目录，请先运行 scripts/prepare_wfcd.py")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


@lru_cache(maxsize=1)
def item_identifiers():
    by_name, by_path = {}, {}
    for row in catalog_seed()["resources"]:
        by_name.setdefault(normalize_name(row["names"]["en"]), set()).add(row["id"])
        by_path.setdefault(row["id"].casefold(), set()).add(row["id"])
    catalog_seed.cache_clear()
    return (
        {name: next(iter(ids)) for name, ids in by_name.items() if len(ids) == 1},
        {name: next(iter(ids)) for name, ids in by_path.items() if len(ids) == 1},
    )


def canonical_item(resource):
    names, paths = item_identifiers()
    path = resource.identifiers.get("game.ref", resource.id).replace("/StoreItems/", "/")
    target = paths.get(path.casefold()) or names.get(normalize_name(resource.names.get("en", "")))
    if target:
        return resource.model_copy(update={"id": target})
    return resource


def _context(filename, path, value, provenance=None):
    return {
        "dataset": filename,
        "mapping_path": path,
        "value": value,
        **({"provenance": provenance} if provenance else {}),
    }


def relocate_misc(resource):
    meta = resource.metadata
    path = meta.get("mapping_path", [])
    if not path or not isinstance(path[-1], str) or not path[-1].startswith("/Lotus/"):
        return None
    target = item_identifiers()[1].get(path[-1].replace("/StoreItems/", "/").casefold())
    if not target:
        return None
    entry = {"dataset": meta["dataset"], "mapping_path": path, "value": meta.get("value")}
    key = meta["dataset"] + "#" + "/".join(map(str, path))
    return Resource(id=target, names=resource.names, metadata={"legacy_mappings": {key: entry}})


def convert_file(filename, data):
    result = {}

    def add(domain, resource):
        if domain == "Misc":
            moved = relocate_misc(resource)
            if moved:
                domain, resource = "Items", moved
        if domain == "Items":
            resource = canonical_item(resource)
        group = result.setdefault(domain, {})
        if resource.id in group:
            from .patches import merge

            previous = group[resource.id]
            resource = resource.model_copy(
                update={
                    "metadata": merge(previous.metadata, resource.metadata),
                    "aliases": list(dict.fromkeys([*previous.aliases, *resource.aliases])),
                }
            )
        group[resource.id] = resource

    if isinstance(data.get("domain"), str) and isinstance(data.get("resources"), list):
        domain = data["domain"]
        if domain not in DOMAIN_NAMES:
            raise ValueError("初始化文件资源域不受支持")
        for row in data["resources"]:
            resource = Resource.model_validate(row)
            add("Desc" if filename == "nightwave_zh.json" else domain, resource)
        return {name: list(rows.values()) for name, rows in result.items()}
    if filename == "wm_pitems.json":
        market_file = ASSETS / "grq/market.json.gz"
        if market_file.exists():
            with gzip.open(market_file, "rt", encoding="utf-8") as stream:
                allowed = {
                    row["identifiers"]["market.slug"] for row in json.load(stream)["resources"]
                }
            for name, slug in data.items():
                if slug in allowed:
                    prior = result.setdefault("Market", {}).setdefault(slug, Resource(id=slug))
                    result["Market"][slug] = prior.model_copy(
                        update={"aliases": [*prior.aliases, name]}
                    )
    elif filename == "riven_weapons.json":
        with gzip.open(ASSETS / "grq/riven.json.gz", "rt", encoding="utf-8") as stream:
            api = {
                row["identifiers"]["riven.compatibility"]: row
                for row in json.load(stream)["resources"]
            }
        for en, zh in data.items():
            if en not in api:
                continue
            resource = Resource.model_validate(api[en]).model_copy(
                update={"names": {**api[en]["names"], "zh-hans": zh}}
            )
            add("Riven", resource)
    elif filename == "weekly_names.json":
        paths = item_identifiers()[1]
        for key, value in data.items():
            if key.startswith("_"):
                continue
            target = paths.get(key.replace("/storeitems/", "/").casefold())
            if target:
                add(
                    "Items",
                    Resource(
                        id=target, names={"zh-hans": value}, metadata={"legacy_names": {key: value}}
                    ),
                )
            else:
                add(
                    "Desc",
                    Resource(
                        id=key,
                        texts={"zh-hans": value},
                        metadata={"dataset": filename, "mapping_path": [key]},
                    ),
                )
    elif filename.endswith("_bounty_tasks.json"):
        region = filename.split("_")[0]
        for key, pool in data["jobs"].items():
            add(
                "Misc",
                Resource(
                    id=misc_id(filename, ["jobs", key]),
                    names={
                        "zh-hans": {"earth": "地球", "venus": "金星", "deimos": "火卫二"}[region]
                        + "任务池 · "
                        + pool["name"]
                    },
                    identifiers={"bounty.job": key},
                    metadata={
                        **_context(filename, ["jobs", key], pool, data.get("source")),
                        "region": region,
                        "kind": "bounty_task_pool",
                    },
                ),
            )
    elif filename.endswith("_bounty_locations.json"):
        region = filename.split("_")[0]
        from ..localization.resources import raw_mapping

        jobs = raw_mapping("jobs.json")
        tasks = raw_mapping(f"{region}_bounty_tasks.json")["jobs"]
        for i, location in enumerate(data["locations"]):
            value = {
                **location,
                "Jobs": [
                    key
                    if isinstance(key, dict)
                    else {
                        "id": key,
                        "name": jobs.get(key + "Title", tasks.get(key, {}).get("name", key)),
                        "stages": tasks.get(key, {}).get("stages", []),
                    }
                    for key in location["Jobs"]
                ],
            }
            label = location.get("label", "帐篷 " + location["LocationTag"].removeprefix("Tent"))
            value["label"] = label
            add(
                "Misc",
                Resource(
                    id=f"bounty.locations.{region}:{location['LocationTag']}",
                    names={
                        "zh-hans": {"earth": "地球", "venus": "金星", "deimos": "火卫二"}[region]
                        + "据点 · "
                        + label
                    },
                    metadata={
                        **_context(filename, ["locations", i], value, data.get("source")),
                        "region": region,
                        "kind": "bounty_location",
                    },
                ),
            )
    else:
        domain = file_domain(filename)
        for key, value in data.items():
            if key in {
                "source",
                "sources",
                "data_source",
                "_source",
                "author",
                "published",
                "title",
            }:
                continue
            if filename == "ExportRegions_zh.json":
                resource = Resource(
                    id=key,
                    identifiers={"worldstate.node": key},
                    names={"zh-hans": value.get("name", key)},
                    metadata=value,
                )
            elif filename in DESC_FILES:
                if not isinstance(value, str):
                    continue
                resource = Resource(
                    id=key,
                    texts={"zh-hans": value},
                    metadata={"dataset": filename, "mapping_path": [key]},
                )
            elif filename in DROP_FILES:
                resource = Resource(
                    id=key,
                    identifiers={"reward.manifest": key},
                    names={"zh-hans": key.rsplit("/", 1)[-1]},
                    metadata={
                        "kind": "reward_table",
                        "datasets": [filename],
                        "rotations": from_pools(value),
                        "provenance": "https://www.warframe.com/droptables",
                    },
                )
            else:
                # 配置中的映射拆成可维护的条目，不把整份文件或来源链接当成资源。
                if isinstance(value, dict):
                    for child, entry in value.items():
                        label = (
                            entry.get("name", entry.get("title", child))
                            if isinstance(entry, dict)
                            else str(entry)
                            if isinstance(entry, str)
                            else child
                        )
                        add(
                            "Desc" if filename == "nightwave_zh.json" else domain,
                            Resource(
                                id=misc_id(filename, [key, child]),
                                names={"zh-hans": str(label)},
                                metadata=_context(filename, [key, child], entry),
                            ),
                        )
                    continue
                resource = Resource(
                    id=mapped_id(filename, key),
                    names={"zh-hans": str(value) if isinstance(value, str) else key},
                    metadata=_context(filename, [key], value),
                )
            add("Desc" if filename == "nightwave_zh.json" else domain, resource)
    return {name: list(rows.values()) for name, rows in result.items()}


def market_resources(items, current):
    by_external = {
        r.identifiers.get("market.item_id"): r.id
        for r in current.values()
        if r.identifiers.get("market.item_id")
    }
    return [
        Resource(
            id=by_external.get(item.id, item.slug),
            identifiers={
                "market.slug": item.slug,
                "market.item_id": item.id,
                **({"game.ref": item.game_ref} if item.game_ref else {}),
            },
            names={lang: value.name for lang, value in item.i18n.items()},
            metadata={**item.model_dump(mode="json", by_alias=True), "tradable": True},
        )
        for item in items
        if item.tradable
    ]
