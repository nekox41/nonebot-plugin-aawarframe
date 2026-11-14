# 作用：查询仲裁时间表，维护节点评级与每分钟生息精华掉落记录。
# 编写日期：2026-11-14
# 作者：Aameow

import bisect
import gzip
import json
import math
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..initialization.nodes import parse_schedule
from ..localization.resources import ASSETS
from ..models.arbitration import ArbitrationBoard, ArbitrationEntry
from ..models.common import Card, utcnow
from ..models.errors import UserInputError

BEIJING = timezone(timedelta(hours=8))


class ArbitrationService:
    def __init__(self, grq, directory):
        self.lock = threading.RLock()
        self.path = Path(directory) / "mappings/arbitration_overrides.json"
        self.grq = grq
        grq.arbitration = self
        self.nodes = grq.mapping("ExportRegions_zh.json")
        with gzip.open(ASSETS / "arbitrations.csv.gz", "rt", encoding="utf-8") as stream:
            self.schedule = parse_schedule(stream.read())
        self._node_ids = {id(v): k for k, v in self.nodes.items()}
        self.stamps = [r[0] for r in self.schedule]
        self.overrides = json.loads(self.path.read_text()) if self.path.exists() else {}

    def list_nodes(self):
        with self.lock:
            return [
                {
                    **node,
                    "id": key,
                    "arbitration": {**node["arbitration"], **self.overrides.get(key, {})},
                }
                for key, node in self.nodes.items()
                if node.get("arbitration") is not None
            ]

    def save_node(self, node_id, grade, vitus_per_minute):
        if grade not in {"S", "A", "B", "C", "D", "F"}:
            raise ValueError("评级应为 S、A、B、C、D、F")
        if (
            isinstance(vitus_per_minute, bool)
            or not math.isfinite(vitus_per_minute)
            or vitus_per_minute < 0
        ):
            raise ValueError("每分钟掉落数量须为大于等于 0 的有限数值")
        if node_id not in self.nodes or self.nodes[node_id].get("arbitration") is None:
            raise ValueError("此节点不属于仲裁节点")
        with self.lock:
            updated = {
                **self.overrides,
                node_id: {"grade": grade, "vitus_per_minute": vitus_per_minute},
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temp.replace(self.path)
            self.overrides = updated

    def query(self, feature, argument="", now=None):
        now = now or utcnow()
        stamp = int(now.timestamp())
        index = bisect.bisect_right(self.stamps, stamp) - 1
        if index < 0 or stamp >= self.stamps[-1] + 3600:
            raise UserInputError("当前时间超出仲裁时间表范围，请更新资源数据。")
        board = ArbitrationBoard()
        title = "仲裁"
        if feature == "arbitration" and not argument.strip():
            rows = self.schedule[index : index + 2]
            board.current = True
        elif feature == "today_arbitration":
            if argument.strip():
                raise UserInputError("今日仲裁不接受参数。")
            title = "今日仲裁"
            day = now.astimezone(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)
            start, end = int(day.timestamp()), int((day + timedelta(days=1)).timestamp())
            rows = self.schedule[
                bisect.bisect_left(self.stamps, start) : bisect.bisect_left(self.stamps, end)
            ]
            if len(rows) != 24:
                raise UserInputError("今天的仲裁时间表不完整，请更新资源数据。")
        else:
            if feature == "efficient_arbitration":
                if argument.strip():
                    raise UserInputError("高效仲裁不接受参数。")
                title = "高效仲裁"

                def predicate(node):
                    return self._stats(node)["grade"] == "S"
            else:
                query = argument.strip()
                matches = {
                    n["missionType"]
                    for n in self.nodes.values()
                    if query in {n["missionType"], n["missionName"]}
                }
                synonyms = {
                    "资源回收": "MT_PURIFY",
                    "回收": "MT_PURIFY",
                    "转换": "MT_ALCHEMY",
                    "覆涌": "MT_VOID_CASCADE",
                    "洪流": "MT_CORRUPTION",
                }
                if query in synonyms:
                    matches = {synonyms[query]}
                if not matches:
                    raise UserInputError("未找到此任务类型，例如：仲裁生存、仲裁防御、仲裁中断。")
                title = "仲裁 · " + query

                def predicate(node):
                    return node["missionType"] in matches

            rows = []
            for row in self.schedule[index + 1 :]:
                node = self.nodes[row[1]]
                if predicate(node):
                    rows.append(row)
                if len(rows) == 10:
                    break
        for i, (start, key) in enumerate(rows):
            node = self.nodes[key]
            end = datetime.fromtimestamp(start + 3600, timezone.utc)
            remaining = max(0, int((end - now).total_seconds()))
            board.entries.append(
                ArbitrationEntry(
                    node_id=key,
                    node=node["name"],
                    planet=node["systemName"],
                    mission=node["missionName"],
                    faction=node.get("factionName") or node.get("faction") or "无派系",
                    time=datetime.fromtimestamp(start, timezone.utc),
                    remaining=f"{remaining // 60}分{remaining % 60:02d}秒",
                    label=("当前" if i == 0 else "下一场") if board.current else "",
                    grade=self._stats(node)["grade"],
                    vitus_per_minute=self._stats(node)["vitus_per_minute"],
                )
            )
        notes = []
        if not board.current and feature != "today_arbitration" and len(rows) < 10:
            notes.append(f"时间表剩余符合条件的任务只有 {len(rows)} 个。")
        return Card(
            title=title,
            source="https://browse.wf/arbys.txt",
            fetched_at=now,
            arbitration_board=board,
            notes=notes,
        )

    def stats_for(self, key):
        node = self.nodes[key]
        if node["arbitration"] is None:
            return None
        with self.lock:
            return {**node["arbitration"], **self.overrides.get(key, {})}

    def _stats(self, node):
        # 覆盖表只存人工记录；外部更新不会覆盖这些值。
        key = self._node_ids[id(node)]
        return self.stats_for(key)
