"""SQLite-backed event deduplicator for Feishu at-least-once delivery.

Feishu webhooks use at-least-once delivery semantics.  Gateway restarts cause
re-delivery of unacknowledged messages.  An in-memory cache would lose state
across restarts.  This uses SQLite for persistence with TTL-based auto-pruning.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class EventDeduplicator:
    """Deduplicates Feishu events using a persistent SQLite store."""

    def __init__(
        self,
        db_path: Path | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        self._db_path = db_path or (Path.home() / ".yigthinker" / "feishu_dedup.sqlite")
        self._ttl = ttl_seconds
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_events (
                event_id TEXT PRIMARY KEY,
                seen_at  REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_at
            ON seen_events(seen_at)
        """)
        self._conn.commit()

    def is_duplicate(self, event_id: str) -> bool:
        """Return True if this event has been processed before."""
        row = self._conn.execute(
            "SELECT 1 FROM seen_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def record(self, event_id: str) -> None:
        """Record an event as processed.  Also prunes expired entries."""
        now = time.time()
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_events (event_id, seen_at) VALUES (?, ?)",
            (event_id, now),
        )
        self._prune(now)
        self._conn.commit()

    def _prune(self, now: float | None = None) -> int:
        """Delete entries older than TTL.  Returns count of pruned rows."""
        cutoff = (now or time.time()) - self._ttl
        cursor = self._conn.execute(
            "DELETE FROM seen_events WHERE seen_at < ?", (cutoff,)
        )
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()
