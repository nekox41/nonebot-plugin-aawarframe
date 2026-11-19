"""仅在 CI/本地构建时下载资源并构建离线数据包（绝不将生成结果提交 Git）。

上游可自动刷新的数据（WFCD/Market/WFCD drops/仲裁）每次从源站更新。
人工整合的汉化/规则源数据暂时使用迁移前的已知历史快照，
直到有明确可重新生成的上游来源；不会声称这些人工映射是实时最新。
任何下载/校验/动态同步失败均使构建失败，不静默发布过期包。
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
PACKAGE = CORE / "nonebot_plugin_aawfcore"
ASSETS = PACKAGE / "assets"

# 源数据来自历史公开 Git blob，并非将已生成快照永久保留在新分支；
# 后续应把人工翻译映射替换为可验证的上游仓库地址。
LEGACY_SOURCE_COMMIT = "e3eb219d1f6614aceaa355aa92c284325be35aa2"
BASE = (
    "https://raw.githubusercontent.com/nekox41/nonebot-plugin-aawarframe/"
    + LEGACY_SOURCE_COMMIT + "/nonebot_plugin_aawarframe/assets/"
)
SEEDS = (
    "ExportRegions_zh.json", "arbitrations.csv.gz", "bounties.json",
    "calendar_tasks.json", "challenge_bounties.json", "descriptions.json",
    "nightwave_zh.json", "operations_zh.json", "rewards.json",
    "riven_stats.json", "variables.json", "weekly_names.json",
    "weekly_rotations.json", "wm_pitems.json",
    "grq/alias-links.json.gz", "grq/droptables.json.gz", "grq/items.json.gz",
    "grq/market.json.gz", "grq/riven.json.gz",
)
MAX_DOWNLOAD = 64 * 1024 * 1024


def download(url: str, target: Path) -> None:
    req = Request(url, headers={"User-Agent": "AAWarframe-Resource-Build/1"})
    with urlopen(req, timeout=45) as stream:
        length = stream.headers.get("Content-Length")
        if length is not None and int(length) > MAX_DOWNLOAD:
            raise ValueError("上游资源超过下载限制：" + target.name)
        data = stream.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError("上游资源超过下载限制：" + target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


async def main() -> None:
    # 运行时资源目录只作为本次构建临时工作区。
    ASSETS.mkdir(parents=True, exist_ok=True)
    for filename in SEEDS:
        target = ASSETS / filename
        print("SEED:", BASE + filename, flush=True)
        await asyncio.to_thread(download, BASE + filename, target)

    sys.path.insert(0, str(CORE))
    import nonebot

    nonebot.init(driver="~none", render={"provider": "playwright", "startup": "off"})
    from nonebot_plugin_aawfcore.grq import GameResourceQuery
    from nonebot_plugin_aawfcore.initialization.build import initialize
    from nonebot_plugin_aawfcore.initialization.pipeline import export_archive, validate

    validate(ASSETS)
    riven_rules = json.loads((ASSETS / "riven_stats.json").read_text(encoding="utf-8"))
    if not isinstance(riven_rules, dict) or not {
        "source", "disposition", "layouts", "attributes"
    }.issubset(riven_rules):
        raise ValueError("紫卡规则资源结构不完整，拒绝构建")
    os.environ["AAWF_BUILD_RESOURCE"] = "1"
    with tempfile.TemporaryDirectory(prefix="aawf-resource-build-") as temp:
        directory = Path(temp)
        latest = await initialize(directory, force=True)
        marker = directory / "resources/current.json"
        state = json.loads(marker.read_text("utf-8"))
        if state.get("network") is not True:
            raise RuntimeError("实时资源更新失败，拒绝用历史种子发布新版本")
        validate(latest)
        db = GameResourceQuery(directory / "registry.sqlite3")
        db.close()
        archive = ASSETS / "offline.tar.gz"
        export_archive(directory, archive, resource_root=latest)
        if archive.stat().st_size < 1024 * 1024:
            raise RuntimeError("生成的离线数据包异常偏小")
        print("Offline archive:", archive.stat().st_size, "bytes")

    # 仅在构建的制品中保留离线包（不是将大量抓取数据作为 Git 源码）。
    for filename in SEEDS:
        # Riven rules are static runtime package data, not part of the versioned game cache.
        if filename != "riven_stats.json":
            (ASSETS / filename).unlink(missing_ok=True)
    (ASSETS / "grq").mkdir(parents=True, exist_ok=True)
    print("Resource provenance: WFCD + Warframe Market + browse.wf and legacy translation seeds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.parse_args()
    asyncio.run(main())
