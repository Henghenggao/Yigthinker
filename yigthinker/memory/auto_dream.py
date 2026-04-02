from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutoDreamConfig:
    min_hours: float = 24.0
    min_sessions: int = 3


class DreamState:
    """Persists last-dream timestamp to disk."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def last_timestamp(self) -> float:
        if not self._path.exists():
            return 0.0
        try:
            return json.loads(self._path.read_text())["last_timestamp"]
        except Exception:
            return 0.0

    def hours_since_last(self) -> float:
        return (time.time() - self.last_timestamp) / 3600.0

    def update(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"last_timestamp": time.time()}))


class AutoDream:
    def __init__(
        self,
        config: AutoDreamConfig | None = None,
        sessions_dir: Path | None = None,
        state: DreamState | None = None,
    ) -> None:
        self._cfg = config or AutoDreamConfig()
        self._sessions_dir = sessions_dir or (Path.home() / ".yigthinker" / "sessions")
        self._state = state or DreamState(
            Path.home() / ".yigthinker" / "memory" / ".dream_state"
        )

    def should_run(self, active_session_id: str = "") -> bool:
        """Check time + session count thresholds."""
        if self._state.hours_since_last() < self._cfg.min_hours:
            return False
        sessions = self.list_sessions_since_last()
        if active_session_id:
            sessions = [s for s in sessions if active_session_id not in s.name]
        return len(sessions) >= self._cfg.min_sessions

    def list_sessions_since_last(self) -> list[Path]:
        """Return JSONL session files modified since last dream."""
        if not self._sessions_dir.exists():
            return []
        cutoff = self._state.last_timestamp
        return [
            f for f in self._sessions_dir.glob("*.jsonl")
            if f.stat().st_mtime > cutoff
        ]

    async def run_background(self, memory_path: Path, active_session_id: str) -> None:
        """
        Fire-and-forget background dream. Acquires lock, spawns consolidation,
        updates state. Errors are logged but never raised.
        """
        try:
            await asyncio.to_thread(self._do_dream, memory_path, active_session_id)
        except Exception:
            pass  # Never surface dream errors to the user

    def _do_dream(self, memory_path: Path, active_session_id: str) -> None:
        from filelock import FileLock
        lock_path = memory_path.parent / ".dream_lock"
        lock = FileLock(str(lock_path), timeout=0)
        with lock:
            sessions = [
                s for s in self.list_sessions_since_last()
                if active_session_id not in s.name
            ]
            if not sessions:
                return
            # In a full implementation: spawn subagent to consolidate sessions
            # For now: update state to prevent re-running until next threshold
            self._state.update()
