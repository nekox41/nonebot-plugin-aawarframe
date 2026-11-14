# 作用：验证离线资源恢复、已有数据保护、联网失败回退和压缩包路径安全。
# 编写日期：2026-11-14
# 作者：Aameow

import gzip
import io
import json
import sqlite3
import tarfile

import pytest

from nonebot_plugin_aawarframe.initialization import pipeline
from nonebot_plugin_aawarframe.localization.resources import PACKAGED, configure_resources


@pytest.fixture(autouse=True)
def reset_resources():
    yield
    configure_resources(PACKAGED)


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "payload/resources"
    (root / "grq").mkdir(parents=True)
    for name in ("descriptions.json", "bounties.json", "rewards.json"):
        (root / name).write_text("{}")
    (root / "ExportRegions_zh.json").write_text('{"SolNode1":{}}')
    with gzip.open(root / "arbitrations.csv.gz", "wt") as f:
        f.write("3600,SolNode1\n7200,SolNode1\n")
    for name in ("items", "market", "riven", "alias-links", "droptables"):
        with gzip.open(root / "grq" / f"{name}.json.gz", "wt") as f:
            json.dump(
                {"links": [{}]} if name == "alias-links" else {"resources": [{"id": "one"}]}, f
            )
    with sqlite3.connect(tmp_path / "payload/registry.sqlite3") as db:
        db.execute("CREATE TABLE item_aliases(name TEXT)")
        db.execute("INSERT INTO item_aliases VALUES(?)", ("离线别名",))
    (tmp_path / "payload/mappings").mkdir()
    (tmp_path / "payload/mappings/arbitration_overrides.json").write_text(
        '{"SolNode1":{"grade":"S","vitus_per_minute":2.5}}'
    )
    output = tmp_path / "offline.tar.gz"
    with tarfile.open(output, "w:gz") as f:
        f.add(tmp_path / "payload/resources", arcname="resources")
        f.add(tmp_path / "payload/registry.sqlite3", arcname="registry.sqlite3")
        f.add(tmp_path / "payload/mappings", arcname="mappings")
    return output


def test_restore_keeps_seed_aliases_and_never_overwrites_database(archive, tmp_path):
    target = tmp_path / "fresh"
    root = pipeline.restore_archive(archive, target)
    assert root.is_dir()
    assert (
        json.loads((target / "mappings/arbitration_overrides.json").read_text())["SolNode1"][
            "vitus_per_minute"
        ]
        == 2.5
    )
    with sqlite3.connect(target / "registry.sqlite3") as db:
        assert db.execute("SELECT name FROM item_aliases").fetchone()[0] == "离线别名"
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "registry.sqlite3").write_bytes(b"keep-existing-data")
    pipeline.restore_archive(archive, existing)
    assert (existing / "registry.sqlite3").read_bytes() == b"keep-existing-data"


async def test_failed_network_keeps_active_data(archive, tmp_path, monkeypatch):
    target = tmp_path / "data"
    old = pipeline.restore_archive(archive, target)

    def fail(*args):
        raise OSError("network unavailable")

    monkeypatch.setattr(pipeline, "build_latest", fail)
    assert await pipeline.initialize(target, force=True) == old
    state = json.loads((target / "resources/current.json").read_text())
    assert state["network"] is False and state["checked_at"] > 0
    assert (target / "registry.sqlite3").exists()


def test_archive_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as f:
        info = tarfile.TarInfo("../bad")
        info.size = 4
        f.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(ValueError):
        pipeline.restore_archive(archive, tmp_path / "target")
    assert not (tmp_path / "bad").exists()
