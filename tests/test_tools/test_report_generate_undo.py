"""P1-3 per-tool integration: report_generate must snapshot files before writing.

Spec: docs/superpowers/specs/2026-04-14-p1-arch-gaps-design.md §P1-3
Audit: docs/audit/2026-04-17-p1-retroactive-audit.md (P1-3 section)
"""
from __future__ import annotations

import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.reports.report_generate import (
    ReportGenerateInput,
    ReportGenerateTool,
)


def _make_ctx(workspace: str) -> SessionContext:
    ctx = SessionContext(settings={"workspace_dir": workspace})
    ctx.vars.set("df", pd.DataFrame({"a": [1, 2, 3]}))
    return ctx


async def test_report_generate_snapshots_new_file(tmp_path):
    """When report_generate writes to a path that doesn't yet exist,
    it must append one UndoEntry with is_new_file=True and no backup."""
    tool = ReportGenerateTool()
    ctx = _make_ctx(str(tmp_path))
    out = tmp_path / "fresh.csv"
    assert not out.exists()

    result = await tool.execute(
        ReportGenerateInput(
            var_name="df",
            output_path=str(out),
            format="csv",
            title="fresh report",
        ),
        ctx,
    )

    assert not result.is_error, f"tool errored: {result.content}"
    assert len(ctx.undo_stack) == 1
    entry = ctx.undo_stack[-1]
    assert entry.tool_name == "report_generate"
    assert entry.original_path == out
    assert entry.is_new_file is True
    assert entry.backup_path is None


async def test_report_generate_snapshots_existing_file_with_backup(tmp_path):
    """When report_generate overwrites an existing file, it must append one
    UndoEntry with is_new_file=False and a backup file that preserves the
    original contents."""
    tool = ReportGenerateTool()
    ctx = _make_ctx(str(tmp_path))
    out = tmp_path / "existing.csv"
    out.write_text("original,content\n1,2\n", encoding="utf-8")

    result = await tool.execute(
        ReportGenerateInput(
            var_name="df",
            output_path=str(out),
            format="csv",
            title="overwrite",
        ),
        ctx,
    )

    assert not result.is_error
    assert len(ctx.undo_stack) == 1
    entry = ctx.undo_stack[-1]
    assert entry.is_new_file is False
    assert entry.backup_path is not None
    assert entry.backup_path.exists()
    assert entry.backup_path.read_text(encoding="utf-8") == "original,content\n1,2\n"


async def test_report_generate_dry_run_does_not_snapshot(tmp_path):
    """Dry-run must NOT touch the file system, so stack must remain empty."""
    tool = ReportGenerateTool()
    ctx = _make_ctx(str(tmp_path))
    ctx.dry_run = True

    result = await tool.execute(
        ReportGenerateInput(
            var_name="df",
            output_path=str(tmp_path / "never.csv"),
            format="csv",
            title="dry",
        ),
        ctx,
    )

    assert not result.is_error
    assert len(ctx.undo_stack) == 0


async def test_report_generate_snapshot_covers_all_formats(tmp_path):
    """Snapshot must happen once per execute() regardless of format.
    One call across all 5 formats keeps the snapshot hook at the
    dispatch-site, not buried inside each _write_* method."""
    tool = ReportGenerateTool()
    ctx = _make_ctx(str(tmp_path))

    # Run for each format that doesn't require heavy optional deps.
    # (pdf/docx/pptx require reportlab/python-docx/python-pptx; already installed per test extras,
    # but we exercise csv + excel to keep this test fast and dep-stable.)
    for idx, fmt in enumerate(("csv", "excel")):
        out = tmp_path / f"r_{idx}.{fmt if fmt != 'excel' else 'xlsx'}"
        result = await tool.execute(
            ReportGenerateInput(
                var_name="df",
                output_path=str(out),
                format=fmt,  # type: ignore[arg-type]
                title="t",
            ),
            ctx,
        )
        assert not result.is_error, f"{fmt}: {result.content}"

    assert len(ctx.undo_stack) == 2
    assert all(e.tool_name == "report_generate" for e in ctx.undo_stack)
