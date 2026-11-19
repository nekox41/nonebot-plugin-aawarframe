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
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS item_catalog(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS item_aliases(item_id TEXT,name TEXT,key TEXT,PRIMARY KEY(item_id,key));
        CREATE TABLE IF NOT EXISTS item_overrides(id TEXT PRIMARY KEY,patch TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS catalog_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT,revision INTEGER DEFAULT 1);
        -- Game assets only. Market-only offers are separate: they are not game items.
        CREATE TABLE IF NOT EXISTS items(
            id TEXT PRIMARY KEY,
            item_path TEXT NOT NULL UNIQUE,
            cn_name TEXT NOT NULL DEFAULT '',
            en_name TEXT NOT NULL DEFAULT '',
            riven_key TEXT,
            wm_slug TEXT UNIQUE,
            metadata TEXT NOT NULL,
            payload TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_items_riven ON items(riven_key);
        CREATE INDEX IF NOT EXISTS idx_items_cn ON items(cn_name);
        CREATE INDEX IF NOT EXISTS idx_items_en ON items(en_name);
        CREATE TABLE IF NOT EXISTS aliases(
            id INTEGER PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            UNIQUE(item_id, normalized_name)
        );
        CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON aliases(normalized_name);
        CREATE TABLE IF NOT EXISTS market_products(
            slug TEXT PRIMARY KEY,
            game_ref TEXT,
            unmatched_reason TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_aliases(
            slug TEXT NOT NULL REFERENCES market_products(slug) ON DELETE CASCADE,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            PRIMARY KEY(slug, normalized_name)
        );
    """)
    if path:
        path.chmod(0o600)
    return db
