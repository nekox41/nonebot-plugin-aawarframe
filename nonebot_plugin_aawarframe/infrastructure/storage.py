import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def read_json(path: Path) -> Any:
    def read():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    return await asyncio.to_thread(read)


async def write_json(path: Path, value: Any) -> None:
    def write():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            logger.warning("无法持久化缓存 %s", path, exc_info=True)

    await asyncio.to_thread(write)
