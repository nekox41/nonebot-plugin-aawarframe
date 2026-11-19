"""Persistent Wiki OpenSearch cache, isolated from game-item matching.

Wiki search keys are the user's actual inputs. A key maps to an ordered set of
Wiki pages; empty searches and upstream failures never enter this database.
"""

import sqlite3
import threading
from pathlib import Path

from ..models.wiki import WikiEntry, WikiSearchResult


class WikiStore:
    def __init__(self, path: Path | None = None):
        if path is not None:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path) if path is not None else ":memory:", check_same_thread=False)
        self.db.execute("PRAGMA foreign_keys = ON")
        if path is not None:
            self.db.execute("PRAGMA journal_mode = WAL")
            path.chmod(0o600)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS wiki_pages (
                id INTEGER PRIMARY KEY,
                page_name TEXT NOT NULL,
                page_description TEXT NOT NULL,
                page_url TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS wiki_keys (
                keyword TEXT NOT NULL,
                page_id INTEGER NOT NULL REFERENCES wiki_pages(id),
                position INTEGER NOT NULL,
                PRIMARY KEY (keyword, position)
            );
            CREATE INDEX IF NOT EXISTS wiki_keys_page_id ON wiki_keys(page_id);
            """
        )

    def get(self, keyword: str) -> WikiSearchResult | None:
        with self.lock:
            rows = self.db.execute(
                """
                SELECT p.page_name, p.page_description, p.page_url
                FROM wiki_keys AS k
                JOIN wiki_pages AS p ON p.id = k.page_id
                WHERE k.keyword = ?
                ORDER BY k.position
                """,
                (keyword,),
            ).fetchall()
        if not rows:
            return None
        return WikiSearchResult(
            query=keyword,
            entries=[
                WikiEntry(title=title, description=description, url=url)
                for title, description, url in rows
            ],
        )

    def put(self, keyword: str, result: WikiSearchResult) -> None:
        if not result.entries:
            return
        with self.lock, self.db:
            self.db.execute("DELETE FROM wiki_keys WHERE keyword = ?", (keyword,))
            for position, entry in enumerate(result.entries):
                url = str(entry.url)
                self.db.execute(
                    """
                    INSERT INTO wiki_pages(page_name, page_description, page_url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(page_url) DO UPDATE SET
                        page_name=excluded.page_name,
                        page_description=excluded.page_description
                    """,
                    (entry.title, entry.description, url),
                )
                page_id = self.db.execute(
                    "SELECT id FROM wiki_pages WHERE page_url = ?", (url,)
                ).fetchone()[0]
                self.db.execute(
                    "INSERT INTO wiki_keys(keyword, page_id, position) VALUES (?, ?, ?)",
                    (keyword, page_id, position),
                )

    def close(self) -> None:
        with self.lock:
            self.db.close()
