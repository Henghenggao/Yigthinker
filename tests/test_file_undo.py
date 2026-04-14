from __future__ import annotations

import time
from pathlib import Path

from yigthinker.session import SessionContext


def test_session_has_undo_stack():
    ctx = SessionContext()
    assert hasattr(ctx, "undo_stack")
    assert ctx.undo_stack == []


# ---------------------------------------------------------------------------
# snapshot_before_write / undo_file tests
# ---------------------------------------------------------------------------

import shutil
import tempfile
from pathlib import Path as _Path

from yigthinker.tools._file_undo import snapshot_before_write, undo_file


def test_snapshot_existing_file(tmp_path):
    ctx = SessionContext()
    target = tmp_path / "report.pdf"
    target.write_text("original content")

    snapshot_before_write(ctx, "report_generate", target)

    assert len(ctx.undo_stack) == 1
    entry = ctx.undo_stack[0]
    assert entry.tool_name == "report_generate"
    assert entry.is_new_file is False
    assert entry.backup_path.exists()
    assert entry.backup_path.read_text() == "original content"


def test_snapshot_new_file(tmp_path):
    ctx = SessionContext()
    target = tmp_path / "new_report.pdf"
    # File does not exist yet

    snapshot_before_write(ctx, "report_generate", target)

    assert len(ctx.undo_stack) == 1
    entry = ctx.undo_stack[0]
    assert entry.is_new_file is True
    assert entry.backup_path == _Path("")


def test_undo_restores_existing(tmp_path):
    ctx = SessionContext()
    target = tmp_path / "report.pdf"
    target.write_text("original")

    snapshot_before_write(ctx, "report_generate", target)
    target.write_text("modified")  # tool overwrites

    entry = ctx.undo_stack[0]
    undo_file(entry)

    assert target.read_text() == "original"
    assert not entry.backup_path.exists()  # backup cleaned up


def test_undo_deletes_new_file(tmp_path):
    ctx = SessionContext()
    target = tmp_path / "new_report.pdf"

    snapshot_before_write(ctx, "report_generate", target)
    target.write_text("generated")  # tool creates new file

    entry = ctx.undo_stack[0]
    undo_file(entry)

    assert not target.exists()


def test_snapshot_evicts_oldest_when_full(tmp_path):
    ctx = SessionContext()

    for i in range(4):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"content {i}")
        snapshot_before_write(ctx, "tool", f, max_depth=3)

    assert len(ctx.undo_stack) == 3
    # Oldest (file_0) should have been evicted and its backup cleaned up
    assert ctx.undo_stack[0].original_path.name == "file_1.txt"
