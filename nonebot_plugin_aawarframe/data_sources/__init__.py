from typing import Dict, Type, Optional

from .deep_archimedea import DeepArchimedeaSource
from .temporal_archimedea import TemporalArchimedeaSource
from ..core.data_source import ResearchDataSource
from nonebot.log import logger

# 注册表：command_name -> 数据源类
_registry: Dict[str, Type[ResearchDataSource]] = {}


def register_source(name: str, cls: Type[ResearchDataSource]) -> None:
    """
    手动注册数据源类到注册中心

    :param name: 命令名称（如 'time_research'）
    :param cls: 数据源类
    """
    if name in _registry:
        raise KeyError(f"命令 '{name}' 已被注册，请检查是否有重复")
    _registry[name] = cls
    logger.info(f"✅ 已注册数据源: {name} -> {cls.__name__}")  # 或使用 logger

def get_source(cmd_name: str) -> ResearchDataSource:
    """根据命令名获取数据源实例"""
    cls = _registry.get(cmd_name)
    if not cls:
        raise ValueError(f"未找到命令 '{cmd_name}' 对应的数据源")
    return cls()  # 每次调用返回新实例


def list_sources() -> list[str]:
    """列出所有已注册的命令名"""
    return list(_registry.keys())


register_source("temporal_archimedea", TemporalArchimedeaSource)
register_source("deep_archimedea",DeepArchimedeaSource)