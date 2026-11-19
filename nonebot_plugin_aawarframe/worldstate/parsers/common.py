# 作用：实现 parsers 层的 common 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import logging
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ParseError(ValueError):
    pass


def records(raw: dict, field: str, model: type[T]) -> tuple[list[T], list[str]]:
    if field not in raw or not isinstance(raw[field], list):
        raise ParseError(f"{field} 缺失或格式变化，解析失败")
    valid = []
    warnings = []
    for index, record in enumerate(raw[field]):
        try:
            valid.append(model.model_validate(record))
        except (ValueError, TypeError):
            logger.warning("解析 %s[%s] 失败", field, index, exc_info=True)
            warnings.append(f"{field}[{index}] 解析失败，已跳过")
    if raw[field] and not valid:
        raise ParseError(f"{field} 全部记录解析失败")
    return valid, warnings
