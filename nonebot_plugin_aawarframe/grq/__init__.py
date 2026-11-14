# 作用：导出 GRQ 统一查询入口和资源模型。
# 编写日期：2026-11-13
# 作者：Aameow

from .manager import GameResourceQuery, configure_grq, get_grq
from .models import Domain, Resource, SearchResult

__all__ = ["GameResourceQuery", "Domain", "Resource", "SearchResult", "get_grq", "configure_grq"]
