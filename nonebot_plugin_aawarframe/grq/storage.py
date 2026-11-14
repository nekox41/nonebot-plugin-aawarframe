# 作用：保存统一物品目录、人工别名和兼容配置，映射数据由 JSON 维护。
# 编写日期：2026-11-13
# 作者：Aameow

import sqlite3
from pathlib import Path


def connect(path: Path | None):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS item_catalog(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS item_aliases(item_id TEXT,name TEXT,key TEXT,PRIMARY KEY(item_id,key));
        CREATE TABLE IF NOT EXISTS item_overrides(id TEXT PRIMARY KEY,patch TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS catalog_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT,revision INTEGER DEFAULT 1);
    """)
    if path:
        path.chmod(0o600)
    return db
