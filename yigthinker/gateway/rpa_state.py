"""RPA state storage (sync-blocking sqlite3).

Clones the EventDeduplicator pattern from yigthinker/channels/feishu/dedup.py
per Phase 10 CONTEXT.md D-02 + CORR-03: a single sqlite3.Connection held as
an instance attribute, with synchronous blocking calls invoked directly from
async FastAPI route handlers (no threadpool wrapper, no async driver).

Three tables back Phase 10's circuit breaker and dedup state:
  1. callback_dedup          -- idempotent callback_id -> cached decision
  2. checkpoint_attempts     -- rolling 24h window per (workflow, checkpoint)
  3. workflow_llm_calls      -- fixed UTC-midnight day bucket per workflow
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RPAStateStore:
    """Sync-blocking sqlite3 wrapper for RPA dedup + circuit breaker state."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (Path.home() / ".yigthinker" / "rpa" / "state.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI async workers may hit this from
        # different thread contexts; the GIL + sqlite's internal locking
        # make single-connection safe for the gateway's single-process model.
        self._conn = sqlite3.connect(
            str(self._db_path), timeout=5.0, check_same_thread=False,
        )
        # WAL + NORMAL: safer concurrent reads and faster writes than the
        # default rollback journal. Single-process gateway never sees
        # multi-writer contention, but WAL helps the test suite when a
        # previous run left a handle open briefly on NTFS.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            # Non-fatal: fall back to defaults if the filesystem rejects WAL
            # (e.g. some network shares). Functional correctness unaffected.
            pass
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS callback_dedup (
                callback_id   TEXT PRIMARY KEY,
                seen_at       REAL NOT NULL,
                decision_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_callback_dedup_seen_at
                ON callback_dedup(seen_at);

            CREATE TABLE IF NOT EXISTS checkpoint_attempts (
                workflow_name TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL,
                attempted_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoint_attempts_attempted_at
                ON checkpoint_attempts(attempted_at);

            CREATE TABLE IF NOT EXISTS workflow_llm_calls (
                workflow_name TEXT NOT NULL,
                called_at     REAL NOT NULL,
                day_bucket    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_llm_calls_day
                ON workflow_llm_calls(workflow_name, day_bucket);
            """
        )
        self._conn.commit()

    # ───────── callback_dedup ─────────

    def is_duplicate_callback(self, callback_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM callback_dedup WHERE callback_id = ?",
            (callback_id,),
        ).fetchone()
        return row is not None

    def get_cached_decision(self, callback_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT decision_json FROM callback_dedup WHERE callback_id = ?",
            (callback_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def record_callback(
        self, callback_id: str, decision: dict[str, Any],
    ) -> None:
        now = time.time()
        self._conn.execute(
            "INSERT OR IGNORE INTO callback_dedup "
            "(callback_id, seen_at, decision_json) VALUES (?, ?, ?)",
            (callback_id, now, json.dumps(decision, ensure_ascii=False)),
        )
        # TTL prune: drop dedup rows older than 24h
        self._conn.execute(
            "DELETE FROM callback_dedup WHERE seen_at < ?",
            (now - 86400,),
        )
        self._conn.commit()

    # ───────── checkpoint_attempts (rolling 24h) ─────────

    def record_checkpoint_attempt(
        self, workflow_name: str, checkpoint_id: str,
    ) -> int:
        """Insert an attempt and return rolling 24h count for this (wf, checkpoint)."""
        now = time.time()
        self._conn.execute(
            "INSERT INTO checkpoint_attempts "
            "(workflow_name, checkpoint_id, attempted_at) VALUES (?, ?, ?)",
            (workflow_name, checkpoint_id, now),
        )
        # TTL prune: 2-day slack
        self._conn.execute(
            "DELETE FROM checkpoint_attempts WHERE attempted_at < ?",
            (now - 172800,),
        )
        row = self._conn.execute(
            "SELECT COUNT(*) FROM checkpoint_attempts "
            "WHERE workflow_name = ? AND checkpoint_id = ? AND attempted_at > ?",
            (workflow_name, checkpoint_id, now - 86400),
        ).fetchone()
        self._conn.commit()
        return int(row[0] if row else 0)

    # ───────── workflow_llm_calls (fixed UTC day bucket) ─────────

    def record_llm_call(self, workflow_name: str) -> int:
        """Insert a call and return today's count for this workflow."""
        now = time.time()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._conn.execute(
            "INSERT INTO workflow_llm_calls "
            "(workflow_name, called_at, day_bucket) VALUES (?, ?, ?)",
            (workflow_name, now, today),
        )
        # TTL prune: drop buckets older than 7 days
        cutoff = datetime.fromtimestamp(
            now - 7 * 86400, tz=timezone.utc,
        ).strftime("%Y-%m-%d")
        self._conn.execute(
            "DELETE FROM workflow_llm_calls WHERE day_bucket < ?",
            (cutoff,),
        )
        row = self._conn.execute(
            "SELECT COUNT(*) FROM workflow_llm_calls "
            "WHERE workflow_name = ? AND day_bucket = ?",
            (workflow_name, today),
        ).fetchone()
        self._conn.commit()
        return int(row[0] if row else 0)

    def close(self) -> None:
        self._conn.close()
