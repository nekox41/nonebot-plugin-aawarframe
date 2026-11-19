# Desc: 规范化用户名称并保留物品类型语义。
# Date: 2026-11-14
# Author: Aameow

import re
import unicodedata


def normalize_ref(value: str) -> str:
    return value.casefold().replace("/storeitems/", "/")


def normalize_name(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", value).casefold()
        if not c.isspace() and not unicodedata.category(c).startswith("P")
    )


def qualifiers(value: str) -> frozenset[str]:
    key = normalize_name(value)
    found = set()
    for kind, tokens in {
        "prime": ("prime",),
        "set": ("set", "一套", "套装"),
        "blueprint": ("blueprint", "蓝图"),
        "barrel": ("barrel", "枪管"),
        "receiver": ("receiver", "枪机"),
        "stock": ("stock", "枪托"),
        "chassis": ("chassis", "机体"),
        "neuroptics": ("neuroptics", "头部神经光元"),
        "systems": ("systems", "系统"),
    }.items():
        if any(t in key for t in tokens):
            found.add(kind)
    if re.search(r"p(?:一?套|set)$", key):
        found.update(("prime", "set"))
    return frozenset(found)
