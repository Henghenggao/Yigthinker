from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yigthinker.providers.base import LLMProvider
    from yigthinker.memory.patterns import PatternStore

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

# Phase 10 / BHV-05 (CORR-04c): appended at the _consolidate_via_llm call site,
# NOT mutated into DREAM_PROMPT so Phase 5 unit tests keep passing unchanged.
_CANDIDATE_PATTERNS_MARKER = "CANDIDATE_PATTERNS:"

_CANDIDATE_PATTERNS_EXTENSION = """\

--- Pattern Detection (for automation suggestions) ---
Additionally, identify repeated tool sequences across the provided sessions.
For each sequence repeated in 2+ distinct sessions, output a JSON block at the
END of your response (AFTER the markdown memory sections) labeled
"CANDIDATE_PATTERNS:" with the following shape:

CANDIDATE_PATTERNS:
{"patterns": [
  {
    "pattern_id": "sales_monthly_aggregation",
    "description": "Load sales data, aggregate by month, chart results",
    "tool_sequence": ["sql_query", "df_transform", "chart_create"],
    "frequency": 5,
    "estimated_time_saved_minutes": 15,
    "required_connections": ["sqlite"],
    "first_seen": "2026-04-01T10:00:00Z",
    "last_seen": "2026-04-10T14:30:00Z"
  }
]}

If no repeated sequences found, output "CANDIDATE_PATTERNS: {}".
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
        pattern_store: "PatternStore | None" = None,
    ) -> None:
        self._cfg = config or AutoDreamConfig()
        self._sessions_dir = sessions_dir or (Path.home() / ".yigthinker" / "sessions")
        self._state = state or DreamState(
            Path.home() / ".yigthinker" / "memory" / ".dream_state"
        )
        self._memory_dirs = memory_dirs or []
        # Phase 10 / BHV-05: optional PatternStore for cross-session pattern detection.
        # When None, the CANDIDATE_PATTERNS extension still runs in _consolidate_via_llm
        # but the parsed output is discarded (no writes).
        self._pattern_store = pattern_store

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
        """Send session memories to LLM for dedup/merge consolidation.

        Phase 10 / BHV-05 (CORR-04c): appends the CANDIDATE_PATTERNS extension to the
        prompt at this call site (NOT to the DREAM_PROMPT constant). Splits the
        response on the `CANDIDATE_PATTERNS:` marker:
          - Pre-marker text goes to MEMORY.md (existing behavior, regression-safe)
          - Post-marker JSON is parsed and merged into PatternStore if present

        Malformed CANDIDATE_PATTERNS JSON is silently suppressed -- the memory markdown
        write still succeeds and the background dream task completes normally.
        """
        existing = ""
        if existing_global.exists():
            existing = existing_global.read_text(encoding="utf-8").strip()

        prompt = DREAM_PROMPT.format(session_memories=session_memories)
        if existing:
            prompt = (
                f"Existing global memory (update/merge with):\n{existing}\n\n{prompt}"
            )
        # CORR-04c: append the CANDIDATE_PATTERNS extension HERE, not to DREAM_PROMPT.
        prompt = prompt + _CANDIDATE_PATTERNS_EXTENSION

        response = await provider.chat(
            [Message(role="user", content=prompt)], tools=[],
        )
        raw_text = response.text or ""

        # Split on the marker. If the marker is absent, the whole response is the
        # memory markdown (Phase 5 behavior preserved).
        memory_text, _, patterns_blob = raw_text.partition(_CANDIDATE_PATTERNS_MARKER)
        memory_text = memory_text.rstrip()

        # If a patterns blob is present AND we have a store, parse + persist defensively.
        if patterns_blob.strip() and self._pattern_store is not None:
            try:
                self._merge_candidate_patterns(patterns_blob)
            except Exception:
                # Pitfall 7 adapted: malformed JSON or schema mismatch -> silent skip.
                # The memory markdown write below still happens.
                pass

        return memory_text

    def _merge_candidate_patterns(self, patterns_blob: str) -> None:
        """Parse a CANDIDATE_PATTERNS: blob and merge it into PatternStore.

        The blob has already been split off from the main response text. It may
        start with whitespace. Empty payload `{}` is a valid "no patterns found"
        sentinel per the prompt -- handled as a no-op.

        Raises on any parse / shape / write failure -- the caller wraps in try/except.
        """
        assert self._pattern_store is not None  # guarded by caller
        blob = patterns_blob.strip()
        if not blob or blob == "{}":
            return

        parsed = json.loads(blob)
        incoming_patterns = parsed.get("patterns", [])
        if not incoming_patterns:
            return

        # Load existing store, merge, save.
        data = self._pattern_store.load()
        existing_patterns = data.setdefault("patterns", {})

        for candidate in incoming_patterns:
            pid = candidate.get("pattern_id")
            if not pid or not isinstance(pid, str):
                continue
            # Normalize the entry with defaults -- existing entries get UPDATED
            # in place; new entries get inserted with the BHV-04 suppression fields
            # set to their neutral defaults.
            normalized = {
                "pattern_id": pid,
                "description": candidate.get("description", ""),
                "tool_sequence": list(candidate.get("tool_sequence", [])),
                "frequency": int(candidate.get("frequency", 0)),
                "estimated_time_saved_minutes": int(
                    candidate.get("estimated_time_saved_minutes", 0)
                ),
                "required_connections": list(
                    candidate.get("required_connections", [])
                ),
                "first_seen": candidate.get("first_seen"),
                "last_seen": candidate.get("last_seen"),
                "sessions": list(candidate.get("sessions", [])),
                "suppressed": False,
                "suppressed_until": None,
            }

            if pid in existing_patterns:
                # Merge: preserve suppression state from the existing entry;
                # update all other fields from the candidate.
                prior = existing_patterns[pid]
                normalized["suppressed"] = prior.get("suppressed", False)
                normalized["suppressed_until"] = prior.get("suppressed_until")
                # Preserve existing sessions + union with new ones
                prior_sessions = set(prior.get("sessions", []))
                new_sessions = set(normalized["sessions"])
                normalized["sessions"] = sorted(prior_sessions | new_sessions)
            existing_patterns[pid] = normalized

        self._pattern_store.save(data)
