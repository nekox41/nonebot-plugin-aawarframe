# 作用：实现 services 层的 worldstate 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import logging

from ..models.common import Card, DataStatus, Snapshot, utcnow
from ..models.errors import UserInputError
from ..providers.worldstate import WorldStateProvider
from ..worldstate.parsers.common import ParseError
from .archimedea import build_archimedea
from .bounties import BOUNTY_FEATURES, build_bounties, build_bounty_summary
from .calendar import build_calendar
from .cetus import build_cetus
from .circuit import build_circuit
from .clan import build_clan
from .cycles import build_cycle, build_plains
from .fissures import build_fissures, build_void_storms
from .nightwave import build_nightwave
from .operations import build_invasions, build_sortie
from .steel_path import build_steel_path

logger = logging.getLogger(__name__)


class WorldStateService:
    def __init__(self, provider: WorldStateProvider):
        self.provider = provider

    async def query(self, feature: str, *, bounty_index: int | None = None) -> Card:
        if feature == "steel_path":
            return build_steel_path(Snapshot(data={}, source="钢铁精华固定周轮换"), utcnow())
        snapshot = await self.provider.fetch()
        now = utcnow()
        try:
            if feature in {"sortie", "archon"}:
                return build_sortie(snapshot, now, archon=feature == "archon")
            if feature == "invasions":
                return build_invasions(snapshot, now)
            if feature == "calendar":
                return build_calendar(snapshot, now)
            if feature in {"circuit", "incarnons"}:
                return build_circuit(snapshot, now, all_incarnons=feature == "incarnons")
            if feature == "nightwave":
                return build_nightwave(snapshot, now)
            if feature == "bounty_summary":
                return build_bounty_summary(snapshot, now)
            if feature == "plains":
                return build_plains(snapshot, now)
            if feature in {"vallis", "cambion", "duviri"}:
                return build_cycle(snapshot, now, feature)
            if feature == "cetus":
                return build_cetus(snapshot, now)
            if feature == "fissures":
                return build_fissures(snapshot, now)
            if feature == "railjack_fissures":
                return build_void_storms(snapshot, now)
            if feature == "steel_fissures":
                return build_fissures(snapshot, now, hard=True)
            if feature in {"deep", "temporal"}:
                return build_archimedea(snapshot, "CT_LAB" if feature == "deep" else "CT_HEX", now)
            if feature in BOUNTY_FEATURES:
                return build_bounties(snapshot, now, bounty_index, region=BOUNTY_FEATURES[feature])
            if feature == "clan":
                return build_clan(snapshot, now)
            raise ValueError(f"未知功能：{feature}")
        except UserInputError:
            raise
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
