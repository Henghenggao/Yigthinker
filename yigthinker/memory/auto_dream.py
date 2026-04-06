from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yigthinker.providers.base import LLMProvider

from yigthinker.types import Message

DREAM_PROMPT = """\
You are consolidating domain knowledge from multiple analysis sessions into a single memory file.

Merge the session memories below into a unified document. Follow these rules:
1. Deduplicate: if the same fact appears in multiple sessions, keep it once
2. Resolve conflicts: if sessions disagree, keep the most recent finding
3. Prune: if the result exceeds approximately 4000 tokens, remove the least important entries
4. Preserve the section structure exactly as shown

Section structure:
# Data Source Knowledge
# Business Rules & Patterns
# Errors & Corrections
# Key Findings
# Analysis Log

Session memories to consolidate:
{session_memories}

Consolidated memory:
"""


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
        memory_dirs: list[Path] | None = None,
    ) -> None:
        self._cfg = config or AutoDreamConfig()
        self._sessions_dir = sessions_dir or (Path.home() / ".yigthinker" / "sessions")
        self._state = state or DreamState(
            Path.home() / ".yigthinker" / "memory" / ".dream_state"
        )
        self._memory_dirs = memory_dirs or []

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

    async def run_background(
        self,
        memory_path: Path,
        active_session_id: str,
        provider: LLMProvider | None = None,
    ) -> None:
        """
        Fully async background dream. Acquires lock, reads session memories,
        consolidates via LLM, writes global MEMORY.md, updates state.
        Errors are suppressed — never surface dream errors to the user.
        """
        try:
            from filelock import FileLock
            lock_path = memory_path.parent / ".dream_lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = FileLock(str(lock_path), timeout=0)
            with lock:
                sessions = [
                    s for s in self.list_sessions_since_last()
                    if active_session_id not in s.name
                ]
                if not sessions or provider is None:
                    self._state.update()
                    return
                session_memories = self._read_session_memories(sessions)
                if not session_memories.strip():
                    self._state.update()
                    return
                consolidated = await self._consolidate_via_llm(
                    session_memories, memory_path, provider,
                )
                if consolidated and consolidated.strip():
                    memory_path.parent.mkdir(parents=True, exist_ok=True)
                    memory_path.write_text(consolidated, encoding="utf-8")
                self._state.update()
        except Exception:
            pass  # Never surface dream errors

    def _read_session_memories(self, session_files: list[Path]) -> str:
        """Read MEMORY.md files from known memory directories."""
        parts: list[str] = []
        for mem_dir in self._memory_dirs:
            mem_file = mem_dir / "MEMORY.md"
            if mem_file.exists():
                content = mem_file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"--- Session: {mem_dir.name} ---\n{content}")
        return "\n\n".join(parts)

    async def _consolidate_via_llm(
        self,
        session_memories: str,
        existing_global: Path,
        provider: LLMProvider,
    ) -> str:
        """Send session memories to LLM for dedup/merge consolidation."""
        existing = ""
        if existing_global.exists():
            existing = existing_global.read_text(encoding="utf-8").strip()

        prompt = DREAM_PROMPT.format(session_memories=session_memories)
        if existing:
            prompt = (
                f"Existing global memory (update/merge with):\n{existing}\n\n{prompt}"
            )
        response = await provider.chat(
            [Message(role="user", content=prompt)], tools=[],
        )
        return response.text
