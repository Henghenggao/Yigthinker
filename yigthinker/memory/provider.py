"""MemoryProvider — agent-private session-scoped memory abstraction.

IMPORTANT (spec §4.5.2 one-vote veto): MemoryProvider is strictly separate
from RetrievalProvider (enterprise RAG). Do not conflate.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from filelock import FileLock
from pydantic import BaseModel, Field


MemoryKind = Literal["pattern", "preference", "session_summary", "user_fact"]


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: MemoryKind
    content: str
    session_id: str | None = None      # None = cross-session (agent-wide)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MemoryProvider(Protocol):
    async def write(self, record: MemoryRecord) -> None: ...
    async def read(
        self,
        kind: MemoryKind | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]: ...
    async def delete(self, record_id: str) -> bool: ...
    async def list_sessions(self) -> list[str]: ...


_TOMBSTONE_MARKER = "__tombstone__"


class FileMemoryProvider:
    """JSONL append-only MemoryProvider with filelock concurrency.

    Storage layout:
        <store_dir>/<agent_id>.jsonl
        <store_dir>/<agent_id>.jsonl.lock    (filelock)

    Semantics:
      - write() appends a single JSON line
      - delete() appends a tombstone line; read() hides tombstoned ids
      - compaction (rewrite file without tombstones) runs after
        max_records_before_compact total lines
    """

    def __init__(
        self,
        store_dir: Path | str,
        agent_id: str = "default",
        max_records_before_compact: int = 1000,
        lock_timeout: float = 5.0,
    ):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._agent_id = agent_id
        self._max_records = max_records_before_compact
        self._lock_timeout = lock_timeout
        # Cache a single FileLock instance so nested `with self._lock:` blocks
        # (e.g. write() → _compact_locked() → _read_active_locked()) are
        # reentrant within a process. A fresh FileLock per call would deadlock.
        self._file_lock = FileLock(
            str(self._path) + ".lock", timeout=lock_timeout
        )

    @property
    def _path(self) -> Path:
        return self._dir / f"{self._agent_id}.jsonl"

    @property
    def _lock(self) -> FileLock:
        return self._file_lock

    async def write(self, record: MemoryRecord) -> None:
        line = record.model_dump_json() + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            if self._line_count() > self._max_records:
                self._compact_locked()

    async def read(
        self,
        kind: MemoryKind | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        records = self._read_active_locked()
        if kind is not None:
            records = [r for r in records if r.kind == kind]
        if session_id is not None:
            records = [r for r in records if r.session_id == session_id]
        return records[:limit]

    async def delete(self, record_id: str) -> bool:
        with self._lock:
            active = self._read_active_locked()
            if not any(r.id == record_id for r in active):
                return False
            tombstone = {"__tombstone__": True, "id": record_id}
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(tombstone) + "\n")
            if self._line_count() > self._max_records:
                self._compact_locked()
        return True

    async def list_sessions(self) -> list[str]:
        records = self._read_active_locked()
        return sorted({r.session_id for r in records if r.session_id is not None})

    # ---------- internals ----------

    def _line_count(self) -> int:
        if not self._path.exists():
            return 0
        with self._path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)

    def _read_active_locked(self) -> list[MemoryRecord]:
        """Return active (non-tombstoned) records, most recent first."""
        if not self._path.exists():
            return []
        tombstoned: set[str] = set()
        records: list[MemoryRecord] = []
        with self._lock:
            with self._path.open("r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    obj = json.loads(raw)
                    if obj.get(_TOMBSTONE_MARKER):
                        tombstoned.add(obj["id"])
                    else:
                        records.append(MemoryRecord.model_validate(obj))
        active = [r for r in records if r.id not in tombstoned]
        active.reverse()    # most-recent-first
        return active

    def _compact_locked(self) -> None:
        """Rewrite file excluding tombstoned records. Must be called under lock."""
        active = self._read_active_locked()
        tmp = self._path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in reversed(active):   # back to chronological order
                f.write(r.model_dump_json() + "\n")
        os.replace(tmp, self._path)
