# 作用：首次联网初始化、原子更新资源，以及安全恢复和导出离线资源包。
# 编写日期：2026-11-14
# 作者：Aameow

import asyncio
import gzip
import json
import logging
import re
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from ..localization.resources import ASSETS, PACKAGED, configure_resources
from .nodes import parse_schedule, prepare_nodes

logger = logging.getLogger(__name__)
SCHEMA = 1


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


def restore_archive(archive, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory, prefix=".restore-") as temporary:
        target = Path(temporary)
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            if sum(m.size for m in members) > 2_000_000_000:
                raise ValueError("资源包过大")
            for member in members:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("资源包包含不安全的路径")
            source.extractall(target, filter="data")
        resources = target / "resources"
        validate(resources)
        root = directory / "resources/versions" / ("offline-" + uuid.uuid4().hex)
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(resources, root)
        db = directory / "registry.sqlite3"
        if not db.exists() and (target / "registry.sqlite3").exists():
            shutil.copyfile(target / "registry.sqlite3", db)
            db.chmod(0o600)
        mappings = target / "mappings"
        if mappings.exists():
            destination = directory / "mappings"
            destination.mkdir(exist_ok=True)
            for path in mappings.glob("*.json"):
                if not (destination / path.name).exists():
                    json.loads(path.read_text(encoding="utf-8"))
                    shutil.copyfile(path, destination / path.name)
        publish(directory, root, network=False, attempted=False)
        return root


def validate(root, quick=False):
    required = [
        "descriptions.json",
        "bounties.json",
        "rewards.json",
        "ExportRegions_zh.json",
        "arbitrations.csv.gz",
        "grq/items.json.gz",
        "grq/market.json.gz",
        "grq/riven.json.gz",
        "grq/alias-links.json.gz",
        "grq/droptables.json.gz",
    ]
    for name in required:
        path = root / name
        if not path.is_file():
            raise ValueError("缺少资源：" + name)
        if quick:
            continue
        if name.endswith(".json"):
            json.loads(path.read_text())
        elif name.endswith(".json.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not payload.get("resources") and not payload.get("links"):
                raise ValueError("资源为空：" + name)
    if quick:
        return
    with gzip.open(root / "arbitrations.csv.gz", "rt", encoding="utf-8") as stream:
        schedule = parse_schedule(stream.read())
    nodes = json.loads((root / "ExportRegions_zh.json").read_text())
    if any(node not in nodes for _, node in schedule):
        raise ValueError("仲裁节点映射不完整")


def publish(directory, root, network, attempted=True):
    marker = Path(directory) / "resources/current.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    temp = marker.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "generation": root.name,
                "network": network,
                "checked_at": time.time() if attempted else 0,
            }
        ),
        encoding="utf-8",
    )
    temp.replace(marker)
    configure_resources(root)


def ensure_offline(directory):
    directory = Path(directory)
    marker = directory / "resources/current.json"
    if marker.exists():
        try:
            state = json.loads(marker.read_text())
            name = state["generation"]
            if Path(name).name != name:
                raise ValueError("无效资源目录")
            root = directory / "resources/versions" / name
            validate(root, quick=True)
            configure_resources(root)
            return root
        except (OSError, ValueError, KeyError):
            logger.warning("本地资源目录不完整，恢复随包数据")
    archive = PACKAGED / "offline.tar.gz"
    if archive.exists():
        return restore_archive(archive, directory)
    # 开发目录直接使用可编辑的源 JSON；发布包始终包含离线压缩包。
    validate(PACKAGED)
    configure_resources(PACKAGED)
    return PACKAGED


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
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    base = await asyncio.to_thread(ensure_offline, directory)
    marker = directory / "resources/current.json"
    state = json.loads(marker.read_text()) if marker.exists() else {}
    if (
        not force
        and state.get("schema") == SCHEMA
        and time.time() - state.get("checked_at", 0) < 86400
    ):
        return base
    stop = threading.Event()
    try:
        root = await asyncio.wait_for(
            asyncio.to_thread(build_latest, directory, base, stop), timeout=120
        )
        publish(directory, root, network=True)
        logger.info("资源初始化完成，已使用最新预处理数据")
        return root
    except asyncio.CancelledError:
        stop.set()
        raise
    except Exception as exc:
        stop.set()
        logger.warning("联网初始化未完成，继续使用本地资源：%s", exc)
        publish(directory, base, network=False) if base != PACKAGED else None
        return base


def export_archive(directory, output, resource_root=None):
    directory, output = Path(directory), Path(output)
    root = resource_root or ASSETS.root
    validate(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        db = Path(temporary) / "registry.sqlite3"
        with (
            sqlite3.connect(directory / "registry.sqlite3") as source,
            sqlite3.connect(db) as target,
        ):
            source.backup(target)
        # 离线数据包不携带口令、白名单或服务器专用配置；完整升级备份另行保留。
        with sqlite3.connect(db) as target:
            tables = {
                r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for name in tables - {
                "item_catalog",
                "item_aliases",
                "item_overrides",
                "catalog_meta",
                "settings",
            }:
                target.execute('DROP TABLE "' + name.replace('"', '""') + '"')
            if "settings" in tables:
                target.execute("DELETE FROM settings")
            target.commit()
            target.execute("VACUUM")
        temporary_output = output.with_suffix(".tmp")
        with tarfile.open(temporary_output, "w:gz") as archive:
            for path in sorted(root.rglob("*")):
                if (
                    path.is_file()
                    and path.name != "offline.tar.gz"
                    and path.resolve() not in {output.resolve(), temporary_output.resolve()}
                ):
                    archive.add(
                        path, arcname="resources/" + str(path.relative_to(root)), recursive=False
                    )
            archive.add(db, arcname="registry.sqlite3")
            for path in sorted((directory / "mappings").glob("*.json")):
                archive.add(path, arcname="mappings/" + path.name, recursive=False)
        temporary_output.replace(output)
