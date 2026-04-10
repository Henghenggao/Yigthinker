"""PatternStore — filelocked + atomic-write JSON store for detected automation patterns.

Phase 10 / BHV-04. Clones the `WorkflowRegistry.save_index` atomic-write shape but
lives at `~/.yigthinker/patterns.json` with its own filelock. Detected patterns are
written here by the AutoDream prompt extension (Plan 10-04); the `suggest_automation`
tool (Plan 10-03, same wave) reads them back for the LLM.

Schema (D-18):
{
    "patterns": {
        "<pattern_id>": {
            "pattern_id": str,
            "description": str,
            "tool_sequence": [str, ...],
            "frequency": int,
            "estimated_time_saved_minutes": int,
            "required_connections": [str, ...],
            "first_seen": str,  # ISO 8601 UTC
            "last_seen": str,   # ISO 8601 UTC
            "sessions": [str, ...],
            "suppressed": bool,
            "suppressed_until": str | None,  # ISO 8601 UTC, or None
        }
    }
}

Lazy suppression pruning (CORR-04a): `list_patterns()` and `list_active()` expire
entries whose `suppressed_until` is in the past by re-setting `suppressed=False` and
`suppressed_until=None` at read time. The pruned state is then persisted. No background
pruner.

FileLock reentrancy (Pitfall 5): `suppress()` and `list_patterns(prune=True)` call
`_save_locked()` instead of `save()` while holding the lock to avoid nested
acquisition. `_save_locked()` itself does NOT take the lock.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock


_DEFAULT_SHAPE: dict[str, Any] = {"patterns": {}}


class PatternStore:
    """Filelocked + atomic-write JSON store for detected automation patterns."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".yigthinker" / "patterns.json")
        self._lock = FileLock(str(self._path) + ".lock", timeout=10)

    # ------------------------------------------------------------------ load

    def load(self) -> dict[str, Any]:
        """Raw read from disk. Returns a fresh default shape if the file is missing.

        Does NOT prune expired suppressions — that's `list_patterns` / `list_active`'s
        job. This is the low-level read used by `save`, `suppress`, and tests that
        need to verify on-disk state without triggering the prune side effect.
        """
        if not self._path.exists():
            # Return a NEW dict each call so callers can mutate freely.
            return {"patterns": {}}
        return json.loads(self._path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ save

    def save(self, data: dict[str, Any]) -> None:
        """Atomic write to patterns.json under filelock.

        Acquires the lock then delegates to `_save_locked`. Callers that ALREADY
        hold the lock (e.g. `suppress`, `list_patterns` after a prune) must call
        `_save_locked` directly instead.
        """
        with self._lock:
            self._save_locked(data)

    def _save_locked(self, data: dict[str, Any]) -> None:
        """Atomic write WITHOUT acquiring the lock. Callers must hold `self._lock`.

        Pitfall 5: Nested lock acquisition is fragile under non-reentrant filelock
        backends. This helper lets `suppress` / `list_patterns` write while holding
        the lock, avoiding re-acquisition.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._path.parent), suffix=".tmp",
            )
            content = json.dumps(data, indent=2, ensure_ascii=False)
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = None
            os.replace(tmp_path, str(self._path))
            tmp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # -------------------------------------------------------------- suppress

    def suppress(self, pattern_id: str, days: int = 90) -> bool:
        """Mark a pattern as suppressed for `days` days (default 90 per BHV-04).

        Returns True if the pattern was found and updated, False if the pattern_id
        does not exist in the store.

        Acquires the lock ONCE and uses `_save_locked` to persist the change (no
        nested lock acquisition — Pitfall 5).
        """
        with self._lock:
            data = self.load()
            entry = data.get("patterns", {}).get(pattern_id)
            if entry is None:
                return False
            until = datetime.now(timezone.utc) + timedelta(days=days)
            entry["suppressed"] = True
            entry["suppressed_until"] = until.isoformat()
            self._save_locked(data)
            return True

    # ------------------------------------------------------------ list / read

    def list_patterns(self, *, prune: bool = True) -> dict[str, Any]:
        """Return the full patterns dict, lazily pruning expired suppressions.

        If `prune=True` (default) and any entries had `suppressed_until < now`, the
        pruned state is persisted to disk via `_save_locked` under the lock.

        Returns the top-level `{"patterns": {...}}` shape (matching `load()`).
        """
        if not prune:
            return self.load()

        with self._lock:
            data = self.load()
            changed = self._prune_expired_suppressions(data)
            if changed:
                self._save_locked(data)
            return data

    def list_active(
        self,
        min_frequency: int = 2,
        include_suppressed: bool = False,
    ) -> list[dict[str, Any]]:
        """Return a filtered list of pattern entries for the suggest_automation tool.

        - Lazily prunes expired suppressions (CORR-04a)
        - Filters out patterns with `frequency < min_frequency`
        - Filters out suppressed patterns unless `include_suppressed=True`
        - Returns a NEW list of dict copies (mutation-safe for callers)
        """
        data = self.list_patterns(prune=True)
        out: list[dict[str, Any]] = []
        for _pid, entry in data.get("patterns", {}).items():
            if entry.get("frequency", 0) < min_frequency:
                continue
            if entry.get("suppressed") and not include_suppressed:
                continue
            # Shallow copy so callers can't mutate the on-disk dict.
            out.append(dict(entry))
        return out

    # ---------------------------------------------------------------- prune

    def _prune_expired_suppressions(self, data: dict[str, Any]) -> bool:
        """Mutate `data` in place, clearing `suppressed` on entries whose
        `suppressed_until` is in the past. Returns True if any entry was modified."""
        now = datetime.now(timezone.utc)
        changed = False
        for entry in data.get("patterns", {}).values():
            if not entry.get("suppressed"):
                continue
            until_str = entry.get("suppressed_until")
            if not until_str:
                continue
            try:
                until = datetime.fromisoformat(until_str)
            except (TypeError, ValueError):
                # Malformed — treat as expired for safety.
                entry["suppressed"] = False
                entry["suppressed_until"] = None
                changed = True
                continue
            if until < now:
                entry["suppressed"] = False
                entry["suppressed_until"] = None
                changed = True
        return changed
