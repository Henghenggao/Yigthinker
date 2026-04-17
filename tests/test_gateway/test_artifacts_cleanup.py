"""Tests for sweep_old_artifacts (quick-260416-kyn Task 2).

Verifies the 7-day-mtime-based sweep on gateway shutdown: old files go,
fresh files stay, emptied session dirs are removed, loose files at the root
are left alone, and missing roots are a no-op.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from yigthinker.presence.gateway.artifacts_cleanup import (
    DEFAULT_ARTIFACT_TTL_SECONDS,
    sweep_old_artifacts,
)


TTL = 7 * 24 * 3600  # 7 days


def _backdate(path: Path, seconds_ago: float) -> None:
    target = time.time() - seconds_ago
    os.utime(path, (target, target))


def test_default_ttl_constant_is_seven_days():
    assert DEFAULT_ARTIFACT_TTL_SECONDS == 7 * 24 * 3600


def test_sweep_deletes_old_file(tmp_path):
    root = tmp_path / "artifacts"
    session = root / "sess-1"
    session.mkdir(parents=True)
    old_file = session / "old.xlsx"
    old_file.write_bytes(b"x")
    _backdate(old_file, 8 * 24 * 3600)

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 1
    assert not old_file.exists()


def test_sweep_preserves_fresh_file(tmp_path):
    root = tmp_path / "artifacts"
    session = root / "sess-1"
    session.mkdir(parents=True)
    fresh = session / "new.xlsx"
    fresh.write_bytes(b"x")
    _backdate(fresh, 1 * 24 * 3600)  # 1 day old

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 0
    assert fresh.exists()


def test_sweep_removes_empty_session_dir(tmp_path):
    root = tmp_path / "artifacts"
    session = root / "sess-1"
    session.mkdir(parents=True)
    old = session / "old.xlsx"
    old.write_bytes(b"x")
    _backdate(old, 30 * 24 * 3600)

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 1
    assert counts["dirs_removed"] >= 1
    assert not session.exists()


def test_sweep_leaves_non_empty_session_dir(tmp_path):
    root = tmp_path / "artifacts"
    session = root / "sess-1"
    session.mkdir(parents=True)
    keep = session / "keep.xlsx"
    keep.write_bytes(b"x")
    drop = session / "drop.xlsx"
    drop.write_bytes(b"x")
    _backdate(drop, 30 * 24 * 3600)

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 1
    assert session.exists()
    assert keep.exists()
    assert not drop.exists()


def test_sweep_handles_missing_root_gracefully(tmp_path):
    root = tmp_path / "does_not_exist"
    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 0
    assert counts["dirs_removed"] == 0
    assert counts["errors"] == 0


def test_sweep_ignores_loose_files_at_root(tmp_path):
    """Defensive: we only sweep files under session subdirs — loose files
    at ARTIFACTS_ROOT itself (config, README, etc.) are preserved."""
    root = tmp_path / "artifacts"
    root.mkdir()
    loose = root / "README.txt"
    loose.write_bytes(b"x")
    _backdate(loose, 30 * 24 * 3600)

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 0
    assert loose.exists()


def test_sweep_recurses_into_nested_dirs(tmp_path):
    """session dir can contain nested subdirs; sweep should still find files."""
    root = tmp_path / "artifacts"
    session = root / "sess-1"
    nested = session / "sub"
    nested.mkdir(parents=True)
    old = nested / "old.xlsx"
    old.write_bytes(b"x")
    _backdate(old, 30 * 24 * 3600)

    counts = sweep_old_artifacts(root, now=time.time(), ttl_seconds=TTL)
    assert counts["files_deleted"] == 1
    assert not old.exists()
