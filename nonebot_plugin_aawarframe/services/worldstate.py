import logging

from ..models.common import Card, DataStatus, utcnow
from ..providers.worldstate import WorldStateProvider
from ..worldstate.parsers.common import ParseError
from .archimedea import build_archimedea
from .bounties import build_bounties
from .cetus import build_cetus
from .cycles import build_plains
from .clan import build_clan
from .fissures import build_fissures, build_void_storms

logger = logging.getLogger(__name__)
ARBITRATION_NOTICE = (
    "官方原始世界状态尚未验证可独立提供仲裁排期；当前仲裁、今日仲裁和高效仲裁暂不可用。"
)


class WorldStateService:
    def __init__(self, provider: WorldStateProvider):
        self.provider = provider

    async def query(self, feature: str) -> Card:
        if feature in {"arbitration", "today_arbitration", "efficient_arbitration"}:
            return Card(
                title="仲裁",
                source="官方 WorldState",
                status=DataStatus.UNAVAILABLE,
                notes=[ARBITRATION_NOTICE],
            )
        snapshot = await self.provider.fetch()
        now = utcnow()
        try:
            if feature == "plains":
                return build_plains(snapshot, now)
            if feature == "cetus":
                return build_cetus(snapshot, now)
            if feature == "fissures":
                return build_fissures(snapshot, now)
            if feature == "railjack_fissures":
                return build_void_storms(snapshot, now)
            if feature == "steel_fissures":
                return build_fissures(snapshot, now, hard=True)
            if feature in {"deep", "temporal"}:
                return build_archimedea(snapshot, "CT_LAB" if feature == "deep" else "CT_HEX")
            if feature == "bounties":
                return build_bounties(snapshot, now)
            if feature == "clan":
                return build_clan(snapshot)
            raise ValueError(f"未知功能：{feature}")
        except (ParseError, KeyError, TypeError, ValueError):
            logger.exception("世界状态模块 %s 解析失败", feature)
            return Card(
                title="数据解析失败",
                source=snapshot.source,
                fetched_at=snapshot.fetched_at,
                stale=snapshot.stale,
                status=DataStatus.PARSE_ERROR,
                notes=["此功能的数据字段发生变化，请稍后重试或联系维护者。其他功能可继续查询。"],
            )
