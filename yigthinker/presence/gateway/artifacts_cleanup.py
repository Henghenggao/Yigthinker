"""7-day mtime-based artifact sweep invoked on gateway shutdown.

The ``excel_write`` tool (quick-260416-kyn Task 1) writes under
``~/.yigthinker/artifacts/<session_id>/``. Without a sweeper these files
accumulate forever — a long-running gateway would slowly eat the disk.

Design (see ``.planning/quick/260416-kyn-.../260416-kyn-CONTEXT.md``
§"Locked Decisions — 7-day TTL"):

- Run on ``GatewayServer.stop()`` only (no periodic sweeper, no on-issue
  sweep — the shutdown path is the cheapest place to pay the cost and
  the user already accepts a brief drain at stop time).
- Target: any file under a ``<session_id>/`` subdir whose ``mtime`` is
  older than ``ttl_seconds`` (default 7 days).
- After deleting files, walk each session dir bottom-up and ``rmdir``
  any directory that is now empty.
- Loose files directly at ``ARTIFACTS_ROOT`` (e.g. stray ``README.txt``)
  are left alone — we only sweep inside session subdirs, defensively.
- Exceptions (permission denied, file locked) are counted but never
  propagate. The sweep is a cleanup nicety, not a correctness step.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT: Path = Path.home() / ".yigthinker" / "artifacts"
DEFAULT_ARTIFACT_TTL_SECONDS: int = 7 * 24 * 3600


def sweep_old_artifacts(
    root: Path,
    now: float,
    ttl_seconds: int = DEFAULT_ARTIFACT_TTL_SECONDS,
) -> dict[str, int]:
    """Delete session files older than ``ttl_seconds`` and drop empty dirs.

    Args:
        root: Artifacts root (typically ``ARTIFACTS_ROOT``).
        now: Current unix timestamp (``time.time()``) — parameterized so
             tests can supply a deterministic clock.
        ttl_seconds: Files with ``mtime`` older than ``now - ttl_seconds``
                     are deleted.

    Returns:
        Counters ``{"files_deleted", "dirs_removed", "errors"}`` suitable
        for shutdown logging.
    """
    counts = {"files_deleted": 0, "dirs_removed": 0, "errors": 0}

    if not root.exists():
        return counts

    cutoff = now - ttl_seconds

    for session_dir in _iter_session_dirs(root):
        # ── Delete old files ─────────────────────────────────────
        for f in session_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
            except OSError:
                counts["errors"] += 1
                continue
            if mtime >= cutoff:
                continue
            try:
                f.unlink()
                counts["files_deleted"] += 1
            except OSError:
                counts["errors"] += 1

        # ── Remove empty dirs bottom-up ──────────────────────────
        # We must visit deepest paths first; sorting by depth works.
        all_dirs = [d for d in session_dir.rglob("*") if d.is_dir()]
        all_dirs.sort(key=lambda p: len(p.parts), reverse=True)
        for d in all_dirs:
            try:
                if not any(d.iterdir()):
                    d.rmdir()
                    counts["dirs_removed"] += 1
            except OSError:
                counts["errors"] += 1

        # Finally, drop the session dir itself if now empty.
        try:
            if session_dir.exists() and not any(session_dir.iterdir()):
                session_dir.rmdir()
                counts["dirs_removed"] += 1
        except OSError:
            counts["errors"] += 1

    return counts


def _iter_session_dirs(root: Path):
    """Yield immediate subdirectories of ``root`` (the session buckets).

    Any loose files at ``root`` itself are ignored — we only sweep inside
    named session subdirs.
    """
    try:
        for child in root.iterdir():
            if child.is_dir():
                yield child
    except OSError:
        return
