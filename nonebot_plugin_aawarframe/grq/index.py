# Desc: 从已合并的资源构建按域隔离的只读内存索引。
# Date: 2026-11-14
# Author: Aameow

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .models import Domain, Resource
from .normalizer import normalize_name, normalize_ref, qualifiers
from .rewards import to_pools


@dataclass(frozen=True)
class DomainIndex:
    config: Domain
    resources: Mapping[str, Resource]
    identifiers: Mapping[tuple[str, str], frozenset[str]]
    names: Mapping[str, frozenset[str]]
    external: Mapping[str, frozenset[str]]
    fuzzy: Mapping[frozenset[str], tuple[str, ...]]
    mappings: Mapping[str, dict]
    full_metadata: Mapping[str, bytes]
    local_names: Mapping[str, frozenset[str]]
    shared_aliases: Mapping[str, tuple]


def build(config, resources, full_metadata=None):
    identifiers, names, fuzzy, external, mappings = {}, {}, {}, {}, {}
    for resource in resources.values():
        for namespace, key in resource.identifiers.items():
            identifiers.setdefault((namespace, key), set()).add(resource.id)
            if namespace == "game.ref":
                identifiers.setdefault(("game.ref.normalized", normalize_ref(key)), set()).add(resource.id)
            if resource.enabled:
                external.setdefault(key, set()).add(resource.id)
        if not resource.enabled:
            continue
        for name in [
            resource.id,
            *resource.names.values(),
            *(resource.aliases if config.aliases else []),
        ]:
            key = normalize_name(name)
            if key:
                names.setdefault(key, set()).add(resource.id)

    def put(dataset, path, value):
        target = mappings.setdefault(dataset, {})
        for i, part in enumerate(path[:-1]):
            next_value = [] if isinstance(path[i + 1], int) else {}
            if isinstance(target, list):
                while len(target) <= part:
                    target.append(None)
                if target[part] is None:
                    target[part] = next_value
                target = target[part]
            else:
                target = target.setdefault(part, next_value)
        if isinstance(target, list):
            while len(target) <= path[-1]:
                target.append(None)
            target[path[-1]] = value
        else:
            target[path[-1]] = value

    for resource in resources.values():
        meta = resource.metadata
        if config.name == "Items" and meta.get("legacy_names"):
            mappings.setdefault("weekly_names.json", {}).update(meta["legacy_names"])
        for entry in meta.get("legacy_mappings", {}).values():
            put(entry["dataset"], entry["mapping_path"], entry["value"])
        if config.name == "Droptable" and meta.get("rotations"):
            pools = to_pools(meta["rotations"])
            for dataset in meta.get("datasets", []):
                put(dataset, [resource.id], pools)
            continue
        dataset, path = meta.get("dataset"), meta.get("mapping_path")
        if dataset and path and resource.enabled:
            put(dataset, path, meta.get("value", resource.texts.get("zh-hans")))
    for name in names:
        group = qualifiers(name) if config.semantic_guard else frozenset()
        fuzzy.setdefault(group, []).append(name)
    return DomainIndex(
        config,
        MappingProxyType(resources),
        MappingProxyType({k: frozenset(v) for k, v in identifiers.items()}),
        MappingProxyType({k: frozenset(v) for k, v in names.items()}),
        MappingProxyType({k: frozenset(v) for k, v in external.items()}),
        MappingProxyType({k: tuple(v) for k, v in fuzzy.items()}),
        MappingProxyType(mappings),
        MappingProxyType(full_metadata or {}),
        MappingProxyType({k: frozenset(v) for k, v in names.items()}),
        MappingProxyType({}),
    )
