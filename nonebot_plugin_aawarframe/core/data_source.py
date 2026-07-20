from abc import ABC, abstractmethod
from typing import Any, Dict


class ResearchDataSource(ABC):
    """所有数据源必须实现的抽象基类"""

    @property
    @abstractmethod
    def command_name(self) -> str:
        """命令名称（如 'time_research'），用于路由和注册"""
        pass

    @abstractmethod
    async def fetch(self) -> Dict[str, Any]:
        """获取并转换数据，返回最终用于渲染的字典"""
        pass