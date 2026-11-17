"""订阅规则、事件基线和持久化通知发件箱（SQLite，单进程）。"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .rules import describe

UTC = timezone.utc
CETUS_RULE_JSON = '{"lead_minutes":15}'


@dataclass(frozen=True)
class Subscription:
    id: int
    bot_id: str
    group_id: str
    user_id: str
    kind: str
    created_at: datetime
    rule: dict

    @property
    def label(self) -> str:
        return describe(self.kind, self.rule)


@dataclass(frozen=True)
class Delivery:
    id: int
    subscription_id: int
    bot_id: str
    group_id: str
    user_id: str
    event_at: datetime
    attempts: int
    kind: str = "cetus_night"
    title: str = ""
    detail: str = ""


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
            CREATE TABLE IF NOT EXISTS subscription_poll_state (
                subscription_id INTEGER PRIMARY KEY
                    REFERENCES subscriptions(id) ON DELETE CASCADE,
                last_status TEXT NOT NULL DEFAULT '等待首次检查',
                initialized INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS subscription_seen (
                subscription_id INTEGER NOT NULL
                    REFERENCES subscriptions(id) ON DELETE CASCADE,
                event_key TEXT NOT NULL,
                seen_at REAL NOT NULL,
                PRIMARY KEY (subscription_id, event_key)
            );
            CREATE INDEX IF NOT EXISTS idx_subscription_seen_age
                ON subscription_seen(seen_at);
        """)
        with self.lock, self.db:
            poll_columns = {row["name"] for row in self.db.execute(
                "PRAGMA table_info(subscription_poll_state)"
            )}
            if "initialized" not in poll_columns:
                self.db.execute(
                    "ALTER TABLE subscription_poll_state "
                    "ADD COLUMN initialized INTEGER NOT NULL DEFAULT 0"
                )
                self.db.execute(
                    "UPDATE subscription_poll_state SET initialized=1 "
                    "WHERE subscription_id IN (SELECT DISTINCT subscription_id "
                    "FROM subscription_seen)"
                )
            columns = {row["name"] for row in self.db.execute(
                "PRAGMA table_info(subscription_deliveries)"
            )}
            if "event_title" not in columns:
                self.db.execute(
                    "ALTER TABLE subscription_deliveries "
                    "ADD COLUMN event_title TEXT NOT NULL DEFAULT ''"
                )
            if "event_detail" not in columns:
                self.db.execute(
                    "ALTER TABLE subscription_deliveries "
                    "ADD COLUMN event_detail TEXT NOT NULL DEFAULT ''"
                )
            # 兼容第一版 Draft 中允许任意提前量的夜灵订阅。
            old = self.db.execute(
                "SELECT 1 FROM subscriptions WHERE kind='cetus_night' "
                "AND rule_json<>? LIMIT 1", (CETUS_RULE_JSON,)
            ).fetchone()
            if old:
                self.db.execute("""
                    DELETE FROM subscriptions WHERE kind='cetus_night'
                      AND id NOT IN (
                        SELECT MIN(id) FROM subscriptions WHERE kind='cetus_night'
                        GROUP BY bot_id,group_id,user_id
                      )
                """)
                self.db.execute(
                    "UPDATE subscriptions SET rule_json=? WHERE kind='cetus_night'",
                    (CETUS_RULE_JSON,),
                )
                self.db.execute("""
                    DELETE FROM subscription_deliveries
                    WHERE status IN ('pending','sending') AND subscription_id IN
                      (SELECT id FROM subscriptions WHERE kind='cetus_night')
                """)
        path.chmod(0o600)

    @staticmethod
    def _subscription(row: sqlite3.Row) -> Subscription:
        return Subscription(
            id=row["id"], bot_id=row["bot_id"], group_id=row["group_id"],
            user_id=row["user_id"], kind=row["kind"],
            created_at=_utc(row["created_at"]), rule=json.loads(row["rule_json"]),
        )

    def subscribe(
        self, bot_id: str, group_id: str, user_id: str,
        kind: str = "cetus_night", rule: dict | None = None,
    ) -> tuple[Subscription, bool]:
        if kind == "cetus_night":
            rule = {"lead_minutes": 15}
        if rule is None or not isinstance(rule, dict):
            raise ValueError("订阅规则无效。")
        encoded = json.dumps(rule, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT * FROM subscriptions WHERE bot_id=? AND group_id=? "
                "AND user_id=? AND kind=? AND rule_json=?",
                (bot_id, group_id, user_id, kind, encoded),
            ).fetchone()
            if row:
                return self._subscription(row), False
            count = self.db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE bot_id=? AND group_id=? AND user_id=?",
                (bot_id, group_id, user_id),
            ).fetchone()[0]
            if count >= 10:
                raise ValueError("每个群最多创建 10 条个人订阅。")
            stamp = datetime.now(UTC).timestamp()
            cursor = self.db.execute(
                "INSERT INTO subscriptions (bot_id,group_id,user_id,kind,rule_json,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (bot_id, group_id, user_id, kind, encoded, stamp),
            )
            row = self.db.execute(
                "SELECT * FROM subscriptions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
            return self._subscription(row), True

    def list_for(self, bot_id: str, group_id: str, user_id: str) -> list[Subscription]:
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM subscriptions WHERE bot_id=? AND group_id=? "
                "AND user_id=? ORDER BY id", (bot_id, group_id, user_id),
            ).fetchall()
        return [self._subscription(row) for row in rows]

    def all_active(self) -> list[Subscription]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM subscriptions").fetchall()
        return [self._subscription(row) for row in rows]

    def remove(self, subscription_id: int, bot_id: str, group_id: str, user_id: str) -> bool:
        with self.lock, self.db:
            return bool(self.db.execute(
                "DELETE FROM subscriptions WHERE id=? AND bot_id=? AND group_id=? AND user_id=?",
                (subscription_id, bot_id, group_id, user_id),
            ).rowcount)

    def has_subscription(self, subscription_id: int) -> bool:
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM subscriptions WHERE id=?", (subscription_id,)
            ).fetchone() is not None

    def statuses_for(self, bot_id: str, group_id: str, user_id: str) -> dict[int, str]:
        with self.lock:
            rows = self.db.execute(
                "SELECT s.id, p.last_status FROM subscriptions s "
                "LEFT JOIN subscription_poll_state p ON p.subscription_id=s.id "
                "WHERE s.bot_id=? AND s.group_id=? AND s.user_id=?",
                (bot_id, group_id, user_id),
            ).fetchall()
        return {row["id"]: row["last_status"] or "等待首次检查" for row in rows}

    def set_status(self, subscription_id: int, status: str) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO subscription_poll_state(subscription_id,last_status) "
                "SELECT id,? FROM subscriptions WHERE id=? "
                "ON CONFLICT(subscription_id) DO UPDATE SET last_status=excluded.last_status",
                (status[:160], subscription_id),
            )

    def enqueue(
        self, subscription_id: int, event_key: str, due_at: datetime, event_at: datetime,
        title: str = "", detail: str = "",
    ) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO subscription_deliveries "
                "(subscription_id,event_key,due_at,event_at,next_attempt_at,"
                "event_title,event_detail) "
                "SELECT id,?,?,?,?,?,? FROM subscriptions WHERE id=?",
                (event_key, due_at.timestamp(), event_at.timestamp(),
                 due_at.timestamp(), title[:120], detail[:420], subscription_id),
            )

    def observe(self, subscription_id: int, events: list, now: datetime) -> int:
        """首次同步只设置基线；之后仅对新事件入队（不可因重启重发）。"""
        queued = 0
        with self.lock, self.db:
            state = self.db.execute(
                "SELECT initialized FROM subscription_poll_state WHERE subscription_id=?",
                (subscription_id,),
            ).fetchone()
            initial = state is None or not state["initialized"]
            if initial:
                self.db.execute(
                    "INSERT INTO subscription_poll_state("
                    "subscription_id,last_status,initialized) "
                    "SELECT id,'监控中',1 FROM subscriptions WHERE id=? "
                    "ON CONFLICT(subscription_id) DO UPDATE SET initialized=1",
                    (subscription_id,),
                )
            for event in events:
                created = self.db.execute(
                    "INSERT OR IGNORE INTO subscription_seen(subscription_id,event_key,seen_at) "
                    "SELECT id,?,? FROM subscriptions WHERE id=?",
                    (event.key, now.timestamp(), subscription_id),
                ).rowcount
                if initial or not created or queued >= 3:
                    continue
                if event.due_at < now - timedelta(seconds=90):
                    continue
                self.db.execute(
                    "INSERT OR IGNORE INTO subscription_deliveries "
                    "(subscription_id,event_key,due_at,event_at,next_attempt_at,"
                    "event_title,event_detail) VALUES (?,?,?,?,?,?,?)",
                    (subscription_id, event.key, event.due_at.timestamp(),
                     event.event_at.timestamp(), event.due_at.timestamp(),
                     event.title[:120], event.detail[:420]),
                )
                queued += 1
        return queued

    def recover(self, now: datetime) -> None:
        with self.lock, self.db:
            self.db.execute(
                "UPDATE subscription_deliveries SET status='pending',next_attempt_at=? "
                "WHERE status='sending'", (now.timestamp(),),
            )

    def expire(self, now: datetime, grace_seconds: int = 90) -> None:
        with self.lock, self.db:
            self.db.execute(
                "UPDATE subscription_deliveries SET status='skipped' "
                "WHERE status='pending' AND due_at<?", (now.timestamp()-grace_seconds,),
            )
            self.db.execute(
                "DELETE FROM subscription_deliveries WHERE status IN "
                "('sent','skipped','failed') AND due_at<?",
                (now.timestamp()-7*86400,),
            )
            self.db.execute(
                "DELETE FROM subscription_seen WHERE seen_at<?", (now.timestamp()-30*86400,)
            )

    def claim_due(self, now: datetime, connected_bots: set[str]) -> list[Delivery]:
        if not connected_bots:
            return []
        bots = sorted(connected_bots)
        placeholders = ",".join("?" for _ in bots)
        with self.lock, self.db:
            rows = self.db.execute(
                f"SELECT d.*,s.bot_id,s.group_id,s.user_id,s.kind "
                f"FROM subscription_deliveries d "
                f"JOIN subscriptions s ON s.id=d.subscription_id "
                f"WHERE d.status='pending' AND s.bot_id IN ({placeholders}) "
                f"AND d.next_attempt_at<=? AND d.due_at<=? "
                f"ORDER BY d.due_at,d.id LIMIT 20",
                (*bots, now.timestamp(), now.timestamp()),
            ).fetchall()
            for row in rows:
                self.db.execute(
                    "UPDATE subscription_deliveries SET status='sending', "
                    "attempts=attempts+1 WHERE id=?", (row["id"],),
                )
        return [
            Delivery(
                id=row["id"], subscription_id=row["subscription_id"],
                bot_id=row["bot_id"], group_id=row["group_id"], user_id=row["user_id"],
                event_at=_utc(row["event_at"]), attempts=row["attempts"]+1,
                kind=row["kind"], title=row["event_title"], detail=row["event_detail"],
            ) for row in rows
        ]

    def mark_sent(self, delivery_id: int, now: datetime) -> None:
        with self.lock, self.db:
            self.db.execute(
                "UPDATE subscription_deliveries SET status='sent',sent_at=?,last_error=NULL "
                "WHERE id=?", (now.timestamp(), delivery_id),
            )

    def mark_failed(self, delivery_id: int, attempts: int, now: datetime, error: str) -> None:
        delay = min(60, 5 * 2 ** max(0, attempts-1))
        with self.lock, self.db:
            self.db.execute(
                "UPDATE subscription_deliveries SET status=?,next_attempt_at=?,"
                "last_error=? WHERE id=?",
                ("failed" if attempts >= 5 else "pending",
                 now.timestamp()+delay, error[:200], delivery_id),
            )

    def close(self) -> None:
        with self.lock:
            self.db.close()
