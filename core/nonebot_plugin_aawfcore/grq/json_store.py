# 作用：从 JSON 文件读取节点、描述、任务池和奖励表，提供只读兼容查询。
# 编写日期：2026-11-13
# 作者：Aameow

import copy
import json
from pathlib import Path

from ..localization.resources import ALIASES, ASSETS, expand
from .catalog import snapshot
from .index import build
from .models import Resource
from .patches import merge
from .registry import DOMAINS
from .sources import convert_file


class JsonMappings:
    def __init__(self, directory: Path | None):
        self.directory = directory
        self.data = {}
        files = {p.name: p for p in ASSETS.glob("*.json")}
        if directory and directory.exists():
            files.update({p.name: p for p in directory.glob("*.json")})
        for name, path in files.items():
            self.data[name] = json.loads(path.read_text(encoding="utf-8"))
            if name == "ExportRegions_zh.json" and path.parent != ASSETS.root:
                self.data[name] = merge(json.loads((ASSETS / name).read_text()), self.data[name])
        self.data = expand(self.data)
        for name, data in self.data.items():
            if name.endswith("_bounty_locations.json"):
                region = name.split("_")[0]
                tasks = self.data[f"{region}_bounty_tasks.json"]["jobs"]
                jobs = self.data["jobs.json"]
                for location in data["locations"]:
                    location["Jobs"] = [
                        entry
                        if isinstance(entry, dict)
                        else {
                            "id": entry,
                            "name": jobs.get(
                                entry + "Title", tasks.get(entry, {}).get("name", entry)
                            ),
                            "stages": tasks.get(entry, {}).get("stages", []),
                        }
                        for entry in location["Jobs"]
                    ]
        groups = {d.name: {} for d in DOMAINS if d.name not in {"Items", "Market", "Riven"}}
        for name, data in self.data.items():
            if name in {parts[0] for parts in ALIASES.values()} or name in {
                "arbitration_overrides.json",
                "arbitration_tiers.json",
            }:
                continue
            for domain, rows in convert_file(name, data).items():
                if domain in groups:
                    for resource in rows:
                        old = groups[domain].get(resource.id)
                        groups[domain][resource.id] = Resource.model_validate(
                            merge(old.model_dump() if old else {}, resource.model_dump())
                        )
        for row in snapshot("droptables.json.gz")["resources"]:
            groups["Droptable"].setdefault(row["id"], Resource.model_validate(row))
        self.indexes = {d.name: build(d, groups[d.name]) for d in DOMAINS if d.name in groups}

    def mapping(self, filename):
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("无效资源名称")
        if filename not in self.data:
            raise ValueError("未找到 JSON 映射：" + filename)
        return copy.deepcopy(self.data[filename])

    def save(self, filename, data):
        if self.directory is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / filename
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        self.data[filename] = data
