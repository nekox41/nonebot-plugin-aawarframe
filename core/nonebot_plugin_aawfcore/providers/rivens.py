# 作用：实现 providers 层的 rivens 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from ..infrastructure.http import HttpClient
from ..infrastructure.storage import read_json, write_json
from ..models.common import utcnow
from ..models.rivens import RivenSnapshot, parse_riven_records

RIVEN_URL = "https://www-static.warframe.com/repos/weeklyRivensPC.json"
logger = logging.getLogger(__name__)


class RivenProvider:
    def __init__(self, http: HttpClient, cache_dir: Path):
        self.http = http
        self.cache_path = cache_dir / "weekly-rivens-pc.json"
        self.lock = asyncio.Lock()
        self.snapshot: RivenSnapshot | None = None
        self.loaded = False
        self.last_attempt: datetime | None = None

    async def fetch(self) -> RivenSnapshot:
        async with self.lock:
            now = utcnow()
            if not self.loaded:
                self.loaded = True
                persisted = await read_json(self.cache_path)
                if persisted is not None:
                    try:
                        cached = RivenSnapshot.model_validate(persisted)
                        if (
                            cached.source == RIVEN_URL
                            and cached.fetched_at.tzinfo is not None
                            and cached.fetched_at <= now
                        ):
                            self.snapshot = cached
                    except (TypeError, ValueError):
                        logger.warning("紫卡持久化缓存无效，将重新获取")
            if (
                self.snapshot
                and self.snapshot.fetched_at.astimezone(timezone.utc).date() == now.date()
            ):
                return self.snapshot.model_copy(deep=True)
            if self.last_attempt and now - self.last_attempt < timedelta(minutes=15):
                return self._fallback(now)
            self.last_attempt = now
            try:
                response = await self.http.get_response(RIVEN_URL)
                records, skipped = await asyncio.to_thread(parse_riven_records, response.text)
                modified = response.headers.get("Last-Modified")
                updated_at = None
                if modified:
                    try:
                        updated_at = parsedate_to_datetime(modified).astimezone(timezone.utc)
                    except (TypeError, ValueError, OverflowError):
                        logger.warning("官方紫卡文件更新时间格式变化")
                snapshot = RivenSnapshot(
                    data=records,
                    source=RIVEN_URL,
                    fetched_at=utcnow(),
                    source_updated_at=updated_at,
                    skipped_records=skipped,
                )
                await write_json(self.cache_path, snapshot.model_dump(mode="json"))
                self.snapshot = snapshot
                logger.info("官方紫卡周数据同步完成：%s 条记录", len(records))
                return snapshot.model_copy(deep=True)
            except Exception:
                logger.exception("官方紫卡周数据同步失败")
                return self._fallback(utcnow())

    def _fallback(self, now: datetime) -> RivenSnapshot:
        if self.snapshot and now - self.snapshot.fetched_at <= timedelta(days=7):
            return self.snapshot.model_copy(update={"stale": True}, deep=True)
        raise RuntimeError("紫卡周数据暂时不可用，且无有效本地缓存")

    async def run_daily(self) -> None:
        while True:
            try:
                snapshot = await self.fetch()
                now = utcnow()
                if snapshot.stale:
                    delay = 900
                else:
                    midnight = (now + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    delay = max(1, (midnight - now).total_seconds())
            except Exception:
                logger.warning("紫卡日更新稍后重试", exc_info=True)
                delay = 900
            await asyncio.sleep(delay)
