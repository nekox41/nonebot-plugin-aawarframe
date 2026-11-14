# Desc: 管理统一物品目录和别名，按交易标记匹配市场商品，映射直接读取 JSON。
# Date: 2026-11-14
# Author: Aameow

import hashlib
import json
import sqlite3
import threading
import zlib
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from ..localization.resources import ASSETS
from .catalog import merge_market, seed_catalog, snapshot
from .index import build
from .json_store import JsonMappings
from .models import Domain, Resource
from .normalizer import normalize_name, normalize_ref, qualifiers
from .patches import merge
from .search import search
from .storage import connect


class GameResourceQuery:
    def __init__(self, path: Path | None = None):
        self.lock = threading.RLock()
        self.db = connect(path)
        self.version = 0
        self._catalog_key = None
        self.json = JsonMappings(path.parent / "mappings" if path else None)
        riven_data = self.json.data.get("riven.json", snapshot("riven.json.gz"))
        self.rivens = {r["id"]: Resource.model_validate(r) for r in riven_data["resources"]}
        self.links = snapshot("alias-links.json.gz")["links"]
        signature = hashlib.sha256(
            b"unified-items-v1"
            + b"".join(
                (ASSETS / "grq" / name).read_bytes() for name in ("items.json.gz", "market.json.gz")
            )
        ).hexdigest()
        old = self.db.execute("SELECT value FROM catalog_meta WHERE key='seed'").fetchone()
        if not old or old[0] != signature:
            items, slugs = seed_catalog()
            self._migrate(path, items, slugs)
            for row in self.db.execute("SELECT * FROM item_overrides"):
                if row["id"] in items:
                    items[row["id"]] = Resource.model_validate(
                        merge(items[row["id"]].model_dump(), json.loads(row["patch"]))
                    )
            with self.db:
                self.db.execute("DELETE FROM item_catalog")
                self.db.executemany(
                    "INSERT INTO item_catalog VALUES(?,?)",
                    [(r.id, r.model_dump_json()) for r in items.values()],
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO catalog_meta VALUES('seed',?)", (signature,)
                )
            del items
        self._load_items()
        self._refresh()

    def _migrate(self, path, items, slugs):
        tables = {
            r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "grq_resources" not in tables:
            return
        if path:
            backup = path.with_name(path.stem + ".pre-unified-items.sqlite3")
            if not backup.exists():
                with sqlite3.connect(backup) as target:
                    self.db.backup(target)
                backup.chmod(0o600)
        rows = self.db.execute("SELECT * FROM grq_resources").fetchall()
        originals = {}
        for row in sorted(
            rows, key=lambda r: (r["source"] == "wfcd", r["source"] == "market", r["source"])
        ):
            key = (row["domain"], row["id"])
            originals[key] = merge(originals.get(key, {}), json.loads(row["payload"]))
        by_name = {normalize_name(r.names.get("en", "")): r.id for r in items.values()}
        riven_items = {r.id: r.identifiers.get("game.ref") for r in self.rivens.values()}
        refs = {r.id.casefold(): r.id for r in items.values()}

        def target(domain, key):
            resource = originals.get((domain, key), {})
            ids = resource.get("identifiers", {})
            if domain == "Market":
                return slugs.get(ids.get("market.slug", key))
            if domain == "Riven":
                ref = ids.get("game.ref") or riven_items.get(key)
                return refs.get((ref or "").casefold()) or by_name.get(
                    normalize_name(
                        ids.get("riven.compatibility", resource.get("names", {}).get("en", ""))
                    )
                )
            if domain == "Items":
                return refs.get(
                    ids.get("game.ref", key).replace("/StoreItems/", "/").casefold()
                ) or by_name.get(normalize_name(resource.get("names", {}).get("en", "")))
            return None

        with self.db:
            # 保留旧目录中的手工物品，以及来源资料中补充的常用别名。
            for (domain, key), payload in originals.items():
                if domain == "Items" and target(domain, key) is None:
                    items[key] = Resource.model_validate(payload)
                    refs[key.casefold()] = key
                dest = target(domain, key)
                if dest and domain in {"Items", "Market", "Riven"}:
                    base = items[dest]
                    items[dest] = base.model_copy(
                        update={
                            "aliases": list(
                                dict.fromkeys([*base.aliases, *payload.get("aliases", [])])
                            )
                        }
                    )
            for row in self.db.execute("SELECT * FROM grq_overrides").fetchall():
                dest = target(row["domain"], row["id"])
                patch = json.loads(row["patch"])
                if dest and row["domain"] != "Riven":
                    previous = self.db.execute(
                        "SELECT patch FROM item_overrides WHERE id=?", (dest,)
                    ).fetchone()
                    combined = merge(
                        json.loads(previous[0]) if previous else {}, patch, delete_null=False
                    )
                    self.db.execute(
                        "INSERT OR REPLACE INTO item_overrides VALUES(?,?)",
                        (dest, json.dumps(combined)),
                    )
                else:
                    self._export_mapping(
                        originals.get((row["domain"], row["id"]), {}),
                        patch,
                        row["domain"],
                        row["id"],
                    )
            for row in self.db.execute("SELECT * FROM grq_aliases").fetchall():
                dest = target(row["domain"], row["id"])
                if dest and row["enabled"]:
                    self.db.execute(
                        "INSERT OR IGNORE INTO item_aliases VALUES(?,?,?)",
                        (dest, row["name"], normalize_name(row["name"])),
                    )
            # 老表完整保留在升级备份中，运行库不再存储 JSON 映射或 Market 域。
            for table in [
                "grq_resources",
                "grq_overrides",
                "grq_aliases",
                "grq_alias_links",
                "grq_archived",
                "grq_imports",
                "grq_missing",
                "grq_domains",
            ]:
                if table in tables:
                    self.db.execute("DROP TABLE " + table)
        self.json = JsonMappings(self.json.directory)

    def _export_mapping(self, original, patch, domain, key):
        updated = Resource.model_validate(merge(original or {"id": key}, patch))
        meta = updated.metadata
        if domain == "Riven":
            riven_key = key.removeprefix("weapon:")
            if riven_key in self.rivens:
                self.rivens[riven_key] = self.rivens[riven_key].model_copy(
                    update={
                        "metadata": merge(
                            self.rivens[riven_key].metadata, patch.get("metadata", {})
                        )
                    }
                )
                self.json.save(
                    "riven.json",
                    {
                        "domain": "Riven",
                        "resources": [r.model_dump() for r in self.rivens.values()],
                    },
                )
            return
        if domain == "Node":
            data = self.json.mapping("ExportRegions_zh.json")
            data[key] = {**meta, "name": updated.name()}
            self.json.save("ExportRegions_zh.json", data)
            return
        if domain == "Droptable" and meta.get("datasets"):
            from .rewards import to_pools

            for name in meta.get("datasets", []):
                data = self.json.mapping(name)
                data[key] = to_pools(meta["rotations"])
                self.json.save(name, data)
            return
        name, parts = meta.get("dataset"), meta.get("mapping_path")
        if name and parts:
            data = self.json.mapping(name)
            cursor = data
            for part in parts[:-1]:
                cursor = cursor[part]
            cursor[parts[-1]] = meta.get("value", updated.name())
            self.json.save(name, data)
        elif domain == "Desc":
            for name in ("mission_type.json", "faction_type.json", "jobs.json", "conquest_zh.json"):
                data = self.json.mapping(name)
                if key in data:
                    data[key] = updated.name()
                    self.json.save(name, data)
                    return
            self._save_custom_mapping(domain, updated)
        else:
            self._save_custom_mapping(domain, updated)

    def _save_custom_mapping(self, domain, resource):
        if domain not in self.json.indexes:
            return
        filename = "custom-" + domain.lower() + ".json"
        data = self.json.data.get(filename, {"domain": domain, "resources": []})
        rows = {r["id"]: r for r in data["resources"]}
        rows[resource.id] = resource.model_dump()
        self.json.save(filename, {"domain": domain, "resources": list(rows.values())})

    def _load_items(self):
        self._base, self._packed = {}, {}
        for row in self.db.execute("SELECT payload FROM item_catalog"):
            resource = Resource.model_validate_json(row[0])
            self._packed[resource.id] = zlib.compress(
                json.dumps(resource.metadata, ensure_ascii=False).encode(), 1
            )
            summary = {
                k: v
                for k, v in resource.metadata.items()
                if k in {"category", "type", "isPrime", "market_tradable"}
            }
            self._base[resource.id] = resource.model_copy(update={"metadata": summary})

    @staticmethod
    def _add_names(index, entries):
        names = {key: set(ids) for key, ids in index.names.items()}
        for word, target in entries:
            if target in index.resources and normalize_name(word):
                names.setdefault(normalize_name(word), set()).add(target)
        fuzzy = defaultdict(list)
        for name in names:
            fuzzy[qualifiers(name) if index.config.semantic_guard else frozenset()].append(name)
        return replace(
            index,
            names=MappingProxyType({k: frozenset(v) for k, v in names.items()}),
            fuzzy=MappingProxyType({k: tuple(v) for k, v in fuzzy.items()}),
        )

    def _refresh(self):
        aliases = defaultdict(list)
        for row in self.db.execute("SELECT * FROM item_aliases"):
            if row["item_id"] in self._base:
                aliases[row["item_id"]].append(row["name"])
        items = {
            key: r.model_copy(update={"aliases": list(dict.fromkeys([*r.aliases, *aliases[key]]))})
            for key, r in self._base.items()
        }
        item_index = build(Domain(name="Items", title="物品目录"), items, self._packed)
        tradable = {
            key: r for key, r in items.items() if r.enabled and r.metadata.get("market_tradable")
        }
        market = build(Domain(name="Items", title="可交易物品", semantic_guard=True), tradable)
        slug_ids = {r.identifiers["market.slug"]: r.id for r in tradable.values()}
        projections = defaultdict(list)
        for row in self.links:
            if row["source_domain"] == "Items" and row["target_domain"] == "Market":
                projections[row["source_id"]].append(row)
        words = []
        for origin, rows in projections.items():
            source = items.get(origin)
            rows = [r for r in rows if r["target_id"] in slug_ids]
            if source and source.enabled and rows:
                priority = min(r["priority"] for r in rows)
                for row in rows:
                    if row["priority"] == priority:
                        words.extend(
                            (word, slug_ids[row["target_id"]])
                            for word in [
                                *source.aliases,
                                source.names.get("en", ""),
                                source.names.get("zh-hans", ""),
                            ]
                        )
        market = self._add_names(market, words)
        riven = build(Domain(name="Riven", title="紫卡兼容", semantic_guard=True), self.rivens)
        words = []
        for row in self.links:
            if row["source_domain"] == "Items" and row["target_domain"] == "Riven":
                source = items.get(row["source_id"])
                if source and source.enabled:
                    words.extend(
                        (word, row["target_id"])
                        for word in [*source.aliases, *source.names.values()]
                    )
        # 兼容市场别名迁移到对应 Prime 物品后的紫卡查询。
        riven = self._add_names(riven, words)
        self.domains = MappingProxyType({"Items": item_index, "Riven": riven, **self.json.indexes})
        self.market_index = market
        self.version += 1

    def get(self, domain, resource_id, namespace=None):
        index = self.domains.get(domain)
        if index is None:
            return None
        if namespace:
            ids = index.identifiers.get((namespace, resource_id), ())
            if not ids and namespace == "game.ref":
                ids = index.identifiers.get(("game.ref.normalized", normalize_ref(resource_id)), ())
            resource = index.resources[next(iter(ids))] if len(ids) == 1 else None
        else:
            resource = index.resources.get(resource_id)
        if resource is None:
            return None
        result = resource.model_copy(deep=True)
        if domain == "Items":
            result = result.model_copy(
                update={"metadata": json.loads(zlib.decompress(self._packed[resource.id]))}
            )
        if domain == "Node" and hasattr(self, "arbitration"):
            result = result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "arbitration": self.arbitration.stats_for(resource.id),
                    }
                }
            )
        return result

    def search(self, domain, query, allowed_ids=None):
        return search(self.domains[domain], query, allowed_ids)

    def search_market(self, query, allowed_ids=None):
        return search(self.market_index, query, allowed_ids)

    def translate(self, domain, key, lang="zh-hans"):
        resource = self.get(domain, key)
        return resource.name(lang) if resource else key

    def name(self, domain, resource_id, lang="zh-hans"):
        return self.translate(domain, resource_id, lang)

    def mapping(self, filename):
        return self.json.mapping(filename)

    def add_alias(self, item_id, alias):
        alias = alias.strip()
        key = normalize_name(alias)
        with self.lock, self.db:
            if item_id not in self._base or not self._base[item_id].enabled:
                raise ValueError("请选择有效物品")
            if not key or len(alias) > 120:
                raise ValueError("别名应为 1–120 字")
            conflicts = self.domains["Items"].names.get(key, frozenset()) - {item_id}
            if conflicts:
                raise ValueError("此名称已对应其他物品，请使用不同别名")
            self.db.execute(
                "INSERT OR REPLACE INTO item_aliases VALUES(?,?,?)", (item_id, alias, key)
            )
            self._refresh()

    def delete_alias(self, item_id, alias):
        with self.lock, self.db:
            self.db.execute(
                "DELETE FROM item_aliases WHERE item_id=? AND key=?",
                (item_id, normalize_name(alias)),
            )
            self._refresh()

    def list_aliases(self):
        with self.lock:
            return [
                {
                    "item_id": r["item_id"],
                    "alias": r["name"],
                    "name": self._base[r["item_id"]].name(),
                    "name_en": self._base[r["item_id"]].names.get("en", ""),
                    "tradable": self._base[r["item_id"]].metadata.get("market_tradable", False),
                }
                for r in self.db.execute("SELECT * FROM item_aliases ORDER BY key,item_id")
                if r["item_id"] in self._base
            ]

    def sync_market(self, items, version=None):
        signature = version or tuple(
            (i.id, i.slug, i.tradable, i.game_ref, tuple((k, v.name) for k, v in i.i18n.items()))
            for i in items
        )
        with self.lock:
            if signature == self._catalog_key:
                return
            if (
                not items
                or len({i.id for i in items}) != len(items)
                or len({i.slug for i in items}) != len(items)
            ):
                raise ValueError("市场目录为空或存在重复标识")
            from .sources import market_resources

            current = {r.id: self.get("Items", r.id) for r in self._base.values()}
            # 移除已下架商品的交易标记；物品本身和人工别名继续保留。
            for key, r in list(current.items()):
                meta = {**r.metadata, "market_tradable": False}
                ids = {k: v for k, v in r.identifiers.items() if not k.startswith("market.")}
                current[key] = r.model_copy(update={"metadata": meta, "identifiers": ids})
            merged, _ = merge_market(current, market_resources(items, {}))
            with self.db:
                self.db.executemany(
                    "INSERT OR REPLACE INTO item_catalog VALUES(?,?)",
                    [(r.id, r.model_dump_json()) for r in merged.values()],
                )
            self._load_items()
            self._refresh()
            self._catalog_key = signature

    def ensure_rivens(self, available):
        known = {r.identifiers["riven.compatibility"] for r in self.rivens.values()}
        missing = available - known
        if missing:
            with self.lock:
                for name in missing:
                    key = normalize_name(name)
                    self.rivens[key] = Resource(
                        id=key,
                        names={"en": name},
                        identifiers={"riven.compatibility": name},
                        metadata={"weapon_type": "unknown", "weapon_type_label": "未分类"},
                    )
                self._refresh()

    def read_setting(self, key, default):
        with self.lock:
            row = self.db.execute(
                "SELECT value,revision FROM settings WHERE key=?", (key,)
            ).fetchone()
        return (json.loads(row[0]), row[1]) if row else (default, 0)

    def write_setting(self, key, value, revision):
        with self.lock, self.db:
            old = self.db.execute("SELECT revision FROM settings WHERE key=?", (key,)).fetchone()
            if (old[0] if old else 0) != revision:
                raise ValueError("配置已修改，请刷新后重试")
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?,?)",
                (key, json.dumps(value), revision + 1),
            )
        return revision + 1

    def close(self):
        with self.lock:
            self.db.close()


_grq = None


def get_grq():
    global _grq
    if _grq is None:
        _grq = GameResourceQuery()
    return _grq


def configure_grq(grq):
    global _grq
    _grq = grq
