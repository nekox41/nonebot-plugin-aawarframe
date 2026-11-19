"""Build-time-only network resource acquisition (never imported by bot startup)."""

import asyncio
import gzip
import json
import logging
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from ..localization.resources import PACKAGED
from .nodes import parse_schedule, prepare_nodes
from .pipeline import ensure_offline, publish, validate

logger = logging.getLogger(__name__)


def fetch(url, text=False):
    with urlopen(
        Request(
            url,
            headers={
                "User-Agent": "AAWarframe/0.15 (+https://github.com/nekox41/nonebot-plugin-aawarframe)",
                "Language": "zh-hans",
            },
        ),
        timeout=15,
    ) as response:
        body = response.read()
    return body.decode("utf-8") if text else json.loads(body)


def build_latest(directory, base, stop):
    from . import market, rules, wfcd

    stage = Path(tempfile.mkdtemp(prefix=".initialize-", dir=directory))
    try:
        resources = stage / "resources"
        shutil.copytree(
            base, resources, ignore=shutil.ignore_patterns("offline.tar.gz", "__pycache__")
        )
        try:
            revision = fetch("https://api.github.com/repos/WFCD/warframe-items/commits/master")[
                "sha"
            ]
        except Exception:
            # 匿名 GitHub API 额度耗尽时仍可获取默认分支的最新公开文件。
            revision = "master"
        wfcd.prepare(revision, stage / "raw", output=resources / "grq/items.json.gz", stop=stop)
        if stop.is_set():
            raise TimeoutError("初始化已取消")
        market.prepare(output=resources / "grq/market.json.gz")
        time.sleep(0.4)
        rules.main(output=resources / "grq")
        schedule_text = fetch("https://browse.wf/arbys.txt", text=True)
        schedule = parse_schedule(schedule_text)
        regions = fetch("https://browse.wf/warframe-public-export-plus/ExportRegions.json")
        tier_text = fetch(
            "https://raw.githubusercontent.com/calamity-inc/browse.wf/senpai/supplemental-data/arbyTiers.js",
            text=True,
        )
        tiers = dict(re.findall(r'(\w+):\s*"([SABCDF])"', tier_text))
        if not tiers:
            raise ValueError("仲裁评级数据为空")
        existing = json.loads((resources / "ExportRegions_zh.json").read_text())
        descriptions = json.loads((resources / "descriptions.json").read_text())
        nodes = prepare_nodes(existing, regions, schedule, tiers, descriptions)
        (resources / "ExportRegions_zh.json").write_text(
            json.dumps(nodes, ensure_ascii=False), encoding="utf-8"
        )
        with gzip.open(resources / "arbitrations.csv.gz", "wt", encoding="utf-8") as stream:
            stream.write(schedule_text)
        validate(resources)
        if stop.is_set():
            raise TimeoutError("初始化已取消")
        root = Path(directory) / "resources/versions" / ("online-" + uuid.uuid4().hex)
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(resources, root)
        return root
    finally:
        shutil.rmtree(stage, ignore_errors=True)


async def initialize(directory, force=False):
    """Refresh upstream resources for release builds only."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    base = await asyncio.to_thread(ensure_offline, directory)
    stop = threading.Event()
    try:
        root = await asyncio.wait_for(
            asyncio.to_thread(build_latest, directory, base, stop), timeout=120
        )
        publish(directory, root)
        return root
    except asyncio.CancelledError:
        stop.set()
        raise
    except Exception as exc:
        stop.set()
        if force:
            raise RuntimeError("构建时的联网资源生成失败") from exc
        logger.warning("仅构建使用的联网资源更新失败：%s", exc)
        return base
