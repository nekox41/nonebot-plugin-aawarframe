# 作用：手动刷新插件资源、恢复离线数据，或导出可分发的数据压缩包。
# 编写日期：2026-11-14
# 作者：Aameow

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nonebot

nonebot.init(driver="~none", render={"startup": "off"})
from nonebot_plugin_aawarframe.grq import GameResourceQuery  # noqa: E402
from nonebot_plugin_aawarframe.initialization.pipeline import (  # noqa: E402
    ensure_offline,
    export_archive,
    initialize,
    restore_archive,
)

parser = argparse.ArgumentParser(description="初始化或备份 Warframe 插件数据")
parser.add_argument("--data-dir", type=Path, default=Path("data/aawarframe"))
parser.add_argument("--refresh", action="store_true")
parser.add_argument("--restore", type=Path)
parser.add_argument("--export", type=Path)
args = parser.parse_args()
if args.restore:
    restore_archive(args.restore, args.data_dir)
elif args.refresh:
    asyncio.run(initialize(args.data_dir, force=True))
else:
    ensure_offline(args.data_dir)
query = GameResourceQuery(args.data_dir / "registry.sqlite3")
query.close()
if args.export:
    export_archive(args.data_dir, args.export)
    print("数据包已生成：", args.export)
