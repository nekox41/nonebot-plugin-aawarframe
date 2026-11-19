# 作用：仅用随包资源离线初始化、版本切换，以及安全恢复和导出离线资源包。
# 编写日期：2026-11-14
# 作者：Aameow

import gzip
import hashlib
import json
import logging
import shutil
import sqlite3
import tarfile
import tempfile
import uuid
from pathlib import Path

from ..localization.resources import ASSETS, PACKAGED, configure_resources
from .nodes import parse_schedule

logger = logging.getLogger(__name__)
SCHEMA = 1


def restore_archive(archive, directory, *, archive_sha256=None):
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
        publish(directory, root, archive_sha256=archive_sha256)
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


def publish(directory, root, *, archive_sha256=None):
    """Atomically commit a fully validated packaged generation."""
    marker = Path(directory) / "resources/current.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    temp = marker.with_suffix(".tmp")
    temp.write_text(
        json.dumps({
            "schema": SCHEMA,
            "generation": root.name,
            "archive_sha256": archive_sha256,
            "source": "packaged",
        }),
        encoding="utf-8",
    )
    temp.replace(marker)
    configure_resources(root)


def _valid_current(directory):
    marker = directory / "resources/current.json"
    if not marker.is_file():
        return None, {}
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
        name = state["generation"]
        if not isinstance(name, str) or name in {".", ".."} or Path(name).name != name:
            raise ValueError("无效资源目录")
        root = directory / "resources/versions" / name
        validate(root, quick=True)
        return root, state
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("已有本地资源损坏或版本记录无效，准备从安装包恢复")
        return None, {}


def ensure_offline(directory):
    """Select packaged resources only; a changed wheel archive replaces the active snapshot.

    User databases/configuration remain untouched. If an upgraded archive cannot be
    restored, the last valid generation remains active instead of switching halfway.
    """
    directory = Path(directory)
    root, state = _valid_current(directory)
    archive = PACKAGED / "offline.tar.gz"
    if not archive.is_file():
        # Explicitly support editable development trees with unpacked resources.
        if root is not None:
            configure_resources(root)
            return root
        validate(PACKAGED)
        configure_resources(PACKAGED)
        return PACKAGED

    with archive.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    if root is not None and state.get("archive_sha256") == fingerprint:
        configure_resources(root)
        return root

    try:
        restored = restore_archive(archive, directory, archive_sha256=fingerprint)
    except Exception:
        if root is None:
            raise
        logger.exception("随包资源恢复失败，继续使用上次验证通过的离线数据")
        configure_resources(root)
        return root
    logger.info("已启用安装包携带的离线资源：%s", restored.name)
    return restored


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
                "items",
                "aliases",
                "market_products",
                "market_aliases",
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
