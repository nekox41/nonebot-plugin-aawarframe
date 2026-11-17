"""订阅持久化与可靠性有限的通知发件箱。

网络发送不能与 SQLite 事务原子提交：正常运行依赖事件唯一键防重，
在「发送已成功但尚未记录 sent」时崩溃，重启可能重新发送。
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc


@dataclass(frozen=True)
class Subscription:
    id: int
    bot_id: str
    group_id: str
    user_id: str
    kind: str
    lead_minutes: int
    created_at: datetime


@dataclass(frozen=True)
class Delivery:
    id: int
    subscription_id: int
    bot_id: str
    group_id: str
    user_id: str
    lead_minutes: int
    event_at: datetime
    attempts: int


def _utc(value: float) -> datetime:
    return datetime.fromtimestamp(value, UTC)


class SubscriptionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                rule_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(bot_id, group_id, user_id, kind, rule_json)
            );
            CREATE TABLE IF NOT EXISTS subscription_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL
                    REFERENCES subscriptions(id) ON DELETE CASCADE,
                event_key TEXT NOT NULL,
                due_at REAL NOT NULL,
                event_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                sent_at REAL,
                last_error TEXT,
                UNIQUE(subscription_id, event_key)
            );
            CREATE INDEX IF NOT EXISTS idx_subscription_due
                ON subscription_deliveries(status, next_attempt_at, due_at);
        """)
        path.chmod(0o600)

    @staticmethod
    def _subscription(row: sqlite3.Row) -> Subscription:
        return Subscription(
            id=row["id"],
            bot_id=row["bot_id"],
            group_id=row["group_id"],
            user_id=row["user_id"],
            kind=row["kind"],
            lead_minutes=json.loads(row["rule_json"])["lead_minutes"],
            created_at=_utc(row["created_at"]),
        )

    def subscribe(
        self, bot_id: str, group_id: str, user_id: str, lead_minutes: int
    ) -> tuple[Subscription, bool]:
        if not 1 <= lead_minutes <= 90:
            raise ValueError("提醒提前量无效")
        rule_json = json.dumps({"lead_minutes": lead_minutes}, sort_keys=True, separators=(",", ":"))
        with self.lock, self.db:
            existing = self.db.execute(
                """SELECT COUNT(*) FROM subscriptions
                   WHERE bot_id=? AND group_id=? AND user_id=?""",
                (bot_id, group_id, user_id),
            ).fetchone()[0]
            if existing >= 10:
                row = self.db.execute(
                    """SELECT * FROM subscriptions
                       WHERE bot_id=? AND group_id=? AND user_id=?
                         AND kind='cetus_night' AND rule_json=?""",
                    (bot_id, group_id, user_id, rule_json),
                ).fetchone()
                if row is None:
                    raise ValueError("每个群最多创建 10 条个人订阅。")
                return self._subscription(row), False
            now = datetime.now(UTC).timestamp()
            cursor = self.db.execute(
                """INSERT OR IGNORE INTO subscriptions
                   (bot_id,group_id,user_id,kind,rule_json,created_at)
                   VALUES (?, ?, ?, 'cetus_night', ?, ?)""",
                (bot_id, group_id, user_id, rule_json, now),
            )
            row = self.db.execute(
                """SELECT * FROM subscriptions
                   WHERE bot_id=? AND group_id=? AND user_id=?
                     AND kind='cetus_night' AND rule_json=?""",
                (bot_id, group_id, user_id, rule_json),
            ).fetchone()
            return self._subscription(row), cursor.rowcount == 1

    def list_for(self, bot_id: str, group_id: str, user_id: str) -> list[Subscription]:
        with self.lock:
            rows = self.db.execute(
                """SELECT * FROM subscriptions
                   WHERE bot_id=? AND group_id=? AND user_id=? ORDER BY id""",
                (bot_id, group_id, user_id),
            ).fetchall()
        return [self._subscription(row) for row in rows]

    def all_active(self) -> list[Subscription]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM subscriptions").fetchall()
        return [self._subscription(row) for row in rows]

    def remove(self, subscription_id: int, bot_id: str, group_id: str, user_id: str) -> bool:
        with self.lock, self.db:
            cursor = self.db.execute(
                """DELETE FROM subscriptions
                   WHERE id=? AND bot_id=? AND group_id=? AND user_id=?""",
                (subscription_id, bot_id, group_id, user_id),
            )
            return cursor.rowcount == 1

    def has_subscription(self, subscription_id: int) -> bool:
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM subscriptions WHERE id=?", (subscription_id,)
            ).fetchone() is not None

    def enqueue(
        self, subscription_id: int, event_key: str, due_at: datetime, event_at: datetime
    ) -> None:
        with self.lock, self.db:
            # INSERT ... SELECT 可以避免轮询期间用户取消订阅后产生外键错误。
            self.db.execute(
                """INSERT OR IGNORE INTO subscription_deliveries
                   (subscription_id,event_key,due_at,event_at,next_attempt_at)
                   SELECT id,?,?,?,? FROM subscriptions WHERE id=?""",
                (
                    event_key,
                    due_at.timestamp(),
                    event_at.timestamp(),
                    due_at.timestamp(),
                    subscription_id,
                ),
            )

    def recover(self, now: datetime) -> None:
        with self.lock, self.db:
            self.db.execute(
                """UPDATE subscription_deliveries SET status='pending',
                   next_attempt_at=? WHERE status='sending'""",
                (now.timestamp(),),
            )

    def expire(self, now: datetime, grace_seconds: int = 90) -> None:
        with self.lock, self.db:
            self.db.execute(
                """UPDATE subscription_deliveries SET status='skipped'
                   WHERE status='pending' AND due_at<?""",
                (now.timestamp() - grace_seconds,),
            )
            # 限制通知历史增长；不删除尚未完成的发送。
            self.db.execute(
                """DELETE FROM subscription_deliveries
                   WHERE status IN ('sent','skipped','failed') AND due_at<?""",
                (now.timestamp() - 7 * 86400,),
            )

    def claim_due(self, now: datetime, connected_bots: set[str]) -> list[Delivery]:
        if not connected_bots:
            return []
        bots = sorted(connected_bots)
        placeholders = ",".join("?" for _ in bots)
        with self.lock, self.db:
            rows = self.db.execute(
                f"""SELECT d.*,s.bot_id,s.group_id,s.user_id,s.rule_json
                    FROM subscription_deliveries d
                    JOIN subscriptions s ON s.id=d.subscription_id
                    WHERE d.status='pending' AND s.bot_id IN ({placeholders})
                      AND d.next_attempt_at<=? AND d.due_at<=?
                    ORDER BY d.due_at,d.id LIMIT 20""",
                (*bots, now.timestamp(), now.timestamp()),
            ).fetchall()
            for row in rows:
                self.db.execute(
                    """UPDATE subscription_deliveries
                       SET status='sending',attempts=attempts+1 WHERE id=?""",
                    (row["id"],),
                )
        return [
            Delivery(
                id=row["id"],
                subscription_id=row["subscription_id"],
                bot_id=row["bot_id"],
                group_id=row["group_id"],
                user_id=row["user_id"],
                lead_minutes=json.loads(row["rule_json"])["lead_minutes"],
                event_at=_utc(row["event_at"]),
                attempts=row["attempts"] + 1,
            )
            for row in rows
        ]

    def mark_sent(self, delivery_id: int, now: datetime) -> None:
        with self.lock, self.db:
            self.db.execute(
                """UPDATE subscription_deliveries
                   SET status='sent',sent_at=?,last_error=NULL WHERE id=?""",
                (now.timestamp(), delivery_id),
            )

    def mark_failed(self, delivery_id: int, attempts: int, now: datetime, error: str) -> None:
        status = "failed" if attempts >= 5 else "pending"
        delay = min(60, 5 * 2 ** max(0, attempts - 1))
        with self.lock, self.db:
            self.db.execute(
                """UPDATE subscription_deliveries
                   SET status=?,next_attempt_at=?,last_error=? WHERE id=?""",
                (status, now.timestamp() + delay, error[:200], delivery_id),
            )

    def close(self) -> None:
        with self.lock:
            self.db.close()
