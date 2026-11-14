# 作用：兼容现有调用，明确选择 GRQ 域读取资料和翻译。
# 编写日期：2026-11-13
# 作者：Aameow

import re

from ..grq import get_grq
from ..grq.normalizer import normalize_name as normalize  # noqa: F401
from .resources import ASSETS  # noqa: F401


def load_mapping(filename: str) -> dict:
    return get_grq().mapping(filename)


def translate(value: str) -> str:
    grq = get_grq()
    for domain in ("Desc",):
        resource = grq.get(domain, value)
        if resource:
            return resource.name()
    return grq.translate("Desc", value)


def node_info(value: str) -> dict:
    grq = get_grq()
    resource = grq.get("Node", value)
    if not resource:
        grq.translate("Node", value)
        return {"name": value}
    return {**resource.metadata, "name": resource.name()}


class ItemResolver:
    def __init__(self, items: list):
        self.grq = get_grq()
        self.grq.sync_market(items)
        self.allowed = {
            resource.id
            for item in items
            if item.tradable
            if (resource := self.grq.get("Items", item.slug, "market.slug"))
        }

    def resolve_result(self, value):
        # 中文名称后的 p 表示 Prime；保留英文原名和自定义别名的精确匹配。
        original = self.grq.search_market(value, self.allowed)
        if original.exact:
            return original
        if re.search(r"(?:[\u4e00-\u9fff]|\s)[pP]$", value.strip()):
            expanded = value.strip()[:-1].rstrip() + " Prime"
            return self.grq.search_market(expanded, self.allowed)
        return original

    def resolve(self, value):
        result = self.resolve_result(value)
        return result.resource.identifiers.get("market.slug") if result.resource else None
