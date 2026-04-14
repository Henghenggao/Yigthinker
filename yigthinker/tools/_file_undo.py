from __future__ import annotations

import shutil
import time
from pathlib import Path

from yigthinker.session import SessionContext, UndoEntry


def snapshot_before_write(
    ctx: SessionContext,
    tool_name: str,
    path: Path,
    max_depth: int = 20,
) -> None:
    """Snapshot a file before a tool overwrites it. Call before writing."""
    if path.exists():
        backup_path = path.parent / f".{path.name}.yig-bak-{len(ctx.undo_stack)}"
        shutil.copy2(path, backup_path)
        entry = UndoEntry(
            tool_name=tool_name,
            original_path=path,
            backup_path=backup_path,
            created_at=time.time(),
            is_new_file=False,
        )
    else:
        entry = UndoEntry(
            tool_name=tool_name,
            original_path=path,
            backup_path=None,
            created_at=time.time(),
            is_new_file=True,
        )

    ctx.undo_stack.append(entry)

    # Evict oldest if over limit
    while len(ctx.undo_stack) > max_depth:
        evicted = ctx.undo_stack.pop(0)
        if evicted.backup_path is not None and evicted.backup_path.exists():
            evicted.backup_path.unlink(missing_ok=True)


def undo_file(entry: UndoEntry) -> None:
    """Undo a single file operation."""
    if entry.is_new_file:
        if entry.original_path.exists():
            entry.original_path.unlink()
    else:
        if entry.backup_path is not None and entry.backup_path.exists():
            shutil.copy2(entry.backup_path, entry.original_path)
            entry.backup_path.unlink(missing_ok=True)


def cleanup_backups(undo_stack: list[UndoEntry]) -> None:
    """Remove all backup files. Called at session end."""
    for entry in undo_stack:
        if entry.backup_path is not None and entry.backup_path.exists():
            entry.backup_path.unlink(missing_ok=True)
