# 作用：合并游戏物品与市场商品，使用稳定物品 ID 保存交易标记。
# 编写日期：2026-11-13
# 作者：Aameow

import gzip
import json
from collections import Counter

from ..localization.resources import ASSETS
from .models import Resource


def snapshot(filename):
    with gzip.open(ASSETS / "grq" / filename, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def merge_market(items, market):
    result = dict(items)
    refs = {
        r.identifiers.get("game.ref", r.id).casefold(): r.id
        for r in items.values()
        if not r.id.startswith("market:")
    }
    # 两种商品可能指向同一内部物品，例如完整守护与套装，仍需保留独立商品身份。
    counts = Counter(
        r.identifiers.get("game.ref", "").replace("/StoreItems/", "/").casefold() for r in market
    )
    claimed = set()
    slugs = {}
    for row in sorted(market, key=lambda r: (r.id.endswith("_set"), r.id)):
        ref = row.identifiers.get("game.ref", "").replace("/StoreItems/", "/")
        target = refs.get(ref.casefold())
        if not target and ref.startswith("/Lotus/") and counts[ref.casefold()] == 1:
            target = ref
        if not target or target in claimed:
            target = "market:" + row.id
        claimed.add(target)
        base = result.get(target)
        names = {**row.names, **(base.names if base else {})}
        aliases = list(
            dict.fromkeys(
                [
                    *(base.aliases if base else []),
                    *row.aliases,
                    *(v for v in row.names.values() if v not in names.values()),
                ]
            )
        )
        identifiers = {**(base.identifiers if base else {}), **row.identifiers}
        if target.startswith("market:") and ref.casefold() in refs:
            identifiers.pop("game.ref", None)
        result[target] = Resource(
            id=target,
            names=names,
            aliases=aliases,
            identifiers=identifiers,
            texts=base.texts if base else {},
            enabled=base.enabled if base else True,
            metadata={
                **(base.metadata if base else {}),
                "market_tradable": row.metadata.get("tradable", True),
                "market": row.metadata,
            },
        )
        slugs[row.id] = target
    return result, slugs


def seed_catalog():
    items = {
        row["id"]: Resource.model_validate(row) for row in snapshot("items.json.gz")["resources"]
    }
    # 保留原有市场常用简称，作为来源名称参与匹配。
    from ..localization.resources import raw_mapping
    from .sources import convert_file

    aliases = {
        r.id: r.aliases
        for r in convert_file("wm_pitems.json", raw_mapping("wm_pitems.json")).get("Market", [])
    }
    market = []
    for row in snapshot("market.json.gz")["resources"]:
        row["aliases"] = list(dict.fromkeys([*row.get("aliases", []), *aliases.get(row["id"], [])]))
        market.append(Resource.model_validate(row))
    return merge_market(items, market)
