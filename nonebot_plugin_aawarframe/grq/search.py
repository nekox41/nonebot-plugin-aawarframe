# 作用：在指定域内执行名称匹配，保护短中文输入和歧义候选。
# 编写日期：2026-11-13
# 作者：Aameow

import re

from rapidfuzz import fuzz, process

from .models import SearchResult
from .normalizer import normalize_name, qualifiers


def search(index, query, allowed_ids=None):
    if not index.config.searchable:
        return SearchResult(status="not_found")
    key = normalize_name(query)
    if not key:
        return SearchResult(status="not_found")
    exact = index.names.get(key, frozenset()) | index.external.get(query, frozenset())
    if allowed_ids is not None:
        exact = exact & allowed_ids
    if exact:
        return SearchResult(
            status="found" if len(exact) == 1 else "ambiguous",
            exact=True,
            candidates=[index.resources[i].model_copy(deep=True) for i in sorted(exact)],
        )
    if not index.config.fuzzy:
        return SearchResult(status="not_found")
    group = qualifiers(query) if index.config.semantic_guard else frozenset()
    names = index.fuzzy.get(group, ())
    if allowed_ids is not None:
        names = tuple(name for name in names if index.names[name] & allowed_ids)
    scores = {}
    for name, score, _ in process.extract(key, names, scorer=fuzz.ratio, score_cutoff=60, limit=30):
        ids = index.names[name]
        if allowed_ids is not None:
            ids = ids & allowed_ids
        for resource_id in ids:
            scores[resource_id] = max(scores.get(resource_id, 0), score)
    ranked = sorted(scores, key=lambda i: (-scores[i], i))[:5]
    if not ranked:
        return SearchResult(status="not_found")
    short = len(key) <= 4 and bool(re.search(r"[\u4e00-\u9fff]", key))
    auto = (
        not short
        and len(key) >= 5
        and scores[ranked[0]] >= 92
        and (len(ranked) == 1 or scores[ranked[0]] - scores[ranked[1]] >= 8)
    )
    selected = ranked[:1] if auto else ranked
    return SearchResult(
        status="found" if auto else "ambiguous",
        candidates=[index.resources[i].model_copy(deep=True) for i in selected],
        scores=[scores[i] for i in selected],
    )
