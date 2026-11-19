"""SQLite projection of verified game-item identities and isolated Market products.

The Resource JSON payload remains for API compatibility, but high-value identities
are first-class indexed columns. Unmatched Market products are never game items.
"""
import json
import sqlite3
from collections import Counter

from .models import Resource
from .normalizer import normalize_name


def persist_catalog(
    db: sqlite3.Connection,
    resources: dict[str, Resource],
    links: list[dict],
) -> None:
    real = {key: row for key, row in resources.items() if not key.startswith("market:")}
    orphan = {key: row for key, row in resources.items() if key.startswith("market:")}
    families: dict[str, str] = {}
    for link in links:
        if link["source_domain"] == "Items" and link["target_domain"] == "Riven":
            source = link["source_id"]
            target = link["target_id"]
            if source in real and source not in families:
                families[source] = target

    wm_slugs = [r.identifiers["market.slug"] for r in real.values()
                if "market.slug" in r.identifiers]
    if len(wm_slugs) != len(set(wm_slugs)):
        raise ValueError("一个市场商品被分配给多个游戏物品")

    by_ref = {r.identifiers.get("game.ref", r.id).replace("/StoreItems/", "/").casefold()
              for r in real.values()}
    all_refs = Counter(
        r.identifiers.get("game.ref", "").replace("/StoreItems/", "/").casefold()
        for r in resources.values() if "market.slug" in r.identifiers
    )

    with db:
        for key, row in real.items():
            metadata = json.dumps(row.metadata, ensure_ascii=False, separators=(",", ":"))
            db.execute(
                "INSERT INTO items(id,item_path,cn_name,en_name,riven_key,wm_slug,"
                "metadata,payload,enabled) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "item_path=excluded.item_path,cn_name=excluded.cn_name,"
                "en_name=excluded.en_name,riven_key=excluded.riven_key,"
                "wm_slug=excluded.wm_slug,metadata=excluded.metadata,"
                "payload=excluded.payload,enabled=excluded.enabled "
                "WHERE items.payload<>excluded.payload "
                "OR items.riven_key IS NOT excluded.riven_key "
                "OR items.enabled<>excluded.enabled",
                (key, row.identifiers.get("game.ref", key).replace("/StoreItems/", "/"),
                 row.names.get("zh-hans", ""), row.names.get("en", ""),
                 families.get(key), row.identifiers.get("market.slug"), metadata,
                 row.model_dump_json(), int(row.enabled)),
            )

        # Products without a verified item identity cannot occupy the items table.
        for row in orphan.values():
            slug = row.identifiers["market.slug"]
            ref = row.identifiers.get("game.ref", "").replace("/StoreItems/", "/")
            if not ref:
                reason = "missing_game_ref"
            elif ref.casefold() not in by_ref:
                reason = "unmatched_game_ref"
            elif all_refs[ref.casefold()] > 1:
                reason = "ambiguous_game_ref"
            else:
                reason = "unresolved_game_ref"
            db.execute(
                "INSERT INTO market_products(slug,game_ref,unmatched_reason,payload)"
                " VALUES(?,?,?,?) ON CONFLICT(slug) DO UPDATE SET "
                "game_ref=excluded.game_ref,unmatched_reason=excluded.unmatched_reason,"
                "payload=excluded.payload WHERE market_products.payload<>excluded.payload "
                "OR market_products.unmatched_reason<>excluded.unmatched_reason",
                (slug, ref or None, reason, row.model_dump_json()),
            )

        # Preserve manually created aliases while migrating from the old table.
        db.execute(
            "INSERT OR IGNORE INTO aliases(item_id,name,normalized_name) "
            "SELECT item_id,name,key FROM item_aliases "
            "WHERE EXISTS(SELECT 1 FROM items WHERE items.id=item_aliases.item_id)"
        )
        db.execute(
            "INSERT OR IGNORE INTO market_aliases(slug,name,normalized_name) "
            "SELECT substr(item_id,8),name,key FROM item_aliases "
            "WHERE item_id LIKE 'market:%' AND EXISTS("
            "SELECT 1 FROM market_products WHERE slug=substr(item_aliases.item_id,8))"
        )

        # Disable missing item identities but keep their aliases and manual overrides.
        db.execute(
            "CREATE TEMP TABLE IF NOT EXISTS current_item_ids(id TEXT PRIMARY KEY)"
        )
        db.execute("DELETE FROM current_item_ids")
        db.executemany(
            "INSERT INTO current_item_ids(id) VALUES(?)", ((key,) for key in real)
        )
        db.execute(
            "UPDATE items SET enabled=0 WHERE id NOT IN (SELECT id FROM current_item_ids)"
        )
        db.execute("DROP TABLE current_item_ids")

        db.execute("CREATE TEMP TABLE IF NOT EXISTS current_market_slugs(slug TEXT PRIMARY KEY)")
        db.execute("DELETE FROM current_market_slugs")
        db.executemany("INSERT INTO current_market_slugs VALUES(?)",
                       ((r.identifiers["market.slug"],) for r in orphan.values()))
        db.execute(
            "DELETE FROM market_products WHERE slug NOT IN "
            "(SELECT slug FROM current_market_slugs)"
        )
        db.execute("DROP TABLE current_market_slugs")


def load_catalog(db: sqlite3.Connection) -> dict[str, Resource]:
    result = {
        row["id"]: Resource.model_validate_json(row["payload"])
        for row in db.execute("SELECT id,payload FROM items WHERE enabled=1")
    }
    for record in db.execute("SELECT payload FROM market_products"):
        row = Resource.model_validate_json(record["payload"])
        result[row.id] = row
    return result


def report_unmatched(db: sqlite3.Connection) -> dict:
    counts = {
        row["unmatched_reason"]: row["count"]
        for row in db.execute(
            "SELECT unmatched_reason,COUNT(*) count FROM market_products "
            "GROUP BY unmatched_reason"
        )
    }
    samples = [
        dict(row) for row in db.execute(
            "SELECT slug,game_ref,unmatched_reason FROM market_products "
            "ORDER BY unmatched_reason,slug LIMIT 100"
        )
    ]
    return {"counts": counts, "examples": samples}
