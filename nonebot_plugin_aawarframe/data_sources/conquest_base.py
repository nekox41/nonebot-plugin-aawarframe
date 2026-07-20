# data_sources/conquest_base.py
from abc import abstractmethod
from typing import Any, Dict, Optional
from ..core.data_source import ResearchDataSource
from ..data_fetcher import fetch_world_state
from ..data_processor import transform_to_archimedea_data, extract_conquests

class ConquestDataSource(ResearchDataSource):
    """基于 Conquests 列表的数据源基类（专用于 World State 的 Conquest 类型）"""

    @property
    @abstractmethod
    def conquest_type(self) -> str:
        """需要的 Conquest 类型，如 'CT_HEX' 或 'CT_LAB'"""
        pass

    async def fetch(self) -> Dict[str, Any]:
        raw_data = await fetch_world_state()
        conquests = extract_conquests(raw_data)  # 抽取 Conquests 列表
        target = next((c for c in conquests if c.get('Type') == self.conquest_type), None)
        if not target:
            return {"Missions": [], "Variables": []}
        return transform_to_archimedea_data(target)