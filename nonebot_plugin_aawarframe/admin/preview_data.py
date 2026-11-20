"""Persist complete Card payloads produced by real bot commands for WebUI previews."""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models.common import Card

logger = logging.getLogger(__name__)


class PreviewDataStore:
    """Keep the latest real command result for every command and preview layout."""

    VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data: dict[str, Any] = {"version": self.VERSION, "features": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                isinstance(loaded, dict)
                and loaded.get("version") == self.VERSION
                and isinstance(loaded.get("features"), dict)
            ):
                self.data = loaded
        except (OSError, ValueError):
            logger.warning("管理台实际预览数据文件无法读取，将在下次命令执行后重建。", exc_info=True)

    def record(
        self, feature: str, preview_id: str, arguments: str, card: Card
    ) -> None:
        """Persist the full validated Card before it is rendered for the user."""
        if not feature or not preview_id:
            return
        record = {
            "feature": feature,
            "preview_id": preview_id,
            "arguments": arguments,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "card": card.model_dump(mode="json"),
        }
        with self.lock:
            features = dict(self.data.get("features", {}))
            features[feature] = record
            payload = {
                "version": self.VERSION,
                "updated_at": record["updated_at"],
                "features": features,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
            self.data = payload

    def for_preview(self, preview_id: str) -> dict[str, Any] | None:
        with self.lock:
            candidates = [
                item
                for item in self.data.get("features", {}).values()
                if isinstance(item, dict) and item.get("preview_id") == preview_id
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda item: item.get("updated_at", ""))

    def preview_index(self) -> dict[str, dict[str, str]]:
        with self.lock:
            result: dict[str, dict[str, str]] = {}
            for item in self.data.get("features", {}).values():
                if not isinstance(item, dict) or not item.get("preview_id"):
                    continue
                key = item["preview_id"]
                current = result.get(key)
                if current is None or item.get("updated_at", "") > current.get("updated_at", ""):
                    result[key] = {
                        "feature": str(item.get("feature", "")),
                        "arguments": str(item.get("arguments", "")),
                        "updated_at": str(item.get("updated_at", "")),
                        "title": str(item.get("card", {}).get("title", "")),
                        "status": str(item.get("card", {}).get("status", "")),
                    }
            return result

    def command_features(self) -> list[str]:
        with self.lock:
            return sorted(self.data.get("features", {}))
