"""Durable scheduled reports — persistence + architect-not-executor next_steps.

Motivation (TODOs.md): the old report_schedule tool stored entries only in
ctx.settings — lost on restart. And it returned a flat `{schedule_id, cron,
report_name}` result with no indication of how to actually run the schedule.
That's silent-success for work that doesn't happen.

Fix: file-backed ScheduleRegistry at ~/.yigthinker/scheduled_reports.json
(or settings override) + tool result includes next_steps by deploy target
(local OS scheduler, user-provided hand-off) matching the workflow-tool
pattern (D-02/D-15 architect-not-executor invariant).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.reports.report_schedule import (
    ReportScheduleInput,
    ReportScheduleTool,
    ScheduleRegistry,
)


# ---------------------------------------------------------------------------
# ScheduleRegistry: file-backed store contract
# ---------------------------------------------------------------------------

def test_schedule_registry_starts_empty(tmp_path):
    reg = ScheduleRegistry(base_dir=tmp_path)
    assert reg.list() == []


def test_schedule_registry_add_persists_to_disk(tmp_path):
    reg = ScheduleRegistry(base_dir=tmp_path)
    reg.add({"schedule_id": "abc123", "cron": "0 8 1 * *", "report_name": "pl"})

    # A new registry instance at the same base_dir must see the entry.
    reg2 = ScheduleRegistry(base_dir=tmp_path)
    entries = reg2.list()
    assert len(entries) == 1
    assert entries[0]["schedule_id"] == "abc123"


def test_schedule_registry_remove(tmp_path):
    reg = ScheduleRegistry(base_dir=tmp_path)
    reg.add({"schedule_id": "abc", "cron": "0 0 * * *", "report_name": "daily"})
    reg.add({"schedule_id": "def", "cron": "0 8 * * MON", "report_name": "weekly"})

    removed = reg.remove("abc")
    assert removed is True
    entries = reg.list()
    assert len(entries) == 1
    assert entries[0]["schedule_id"] == "def"


def test_schedule_registry_remove_missing_returns_false(tmp_path):
    reg = ScheduleRegistry(base_dir=tmp_path)
    assert reg.remove("nonexistent") is False


def test_schedule_registry_file_format_is_versioned(tmp_path):
    reg = ScheduleRegistry(base_dir=tmp_path)
    reg.add({"schedule_id": "x", "cron": "* * * * *", "report_name": "r"})

    # The on-disk file must have a "version" field so future format changes
    # can be detected + migrated.
    data = json.loads((tmp_path / "scheduled_reports.json").read_text())
    assert "version" in data
    assert "schedules" in data
    assert isinstance(data["schedules"], list)


# ---------------------------------------------------------------------------
# ReportScheduleTool: integration with registry + architect-not-executor output
# ---------------------------------------------------------------------------

async def test_tool_writes_to_session_settings_for_backward_compat(tmp_path):
    """Existing /schedule CLI command reads ctx.settings['_scheduled_reports']
    — that surface must keep working."""
    reg = ScheduleRegistry(base_dir=tmp_path)
    tool = ReportScheduleTool(registry=reg)
    ctx = SessionContext()
    inp = ReportScheduleInput(
        report_name="monthly_pl",
        cron="0 8 1 * *",
        var_name="pl_data",
        format="excel",
        output_path="/reports/monthly_pl.xlsx",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    schedules = ctx.settings.get("_scheduled_reports", [])
    assert len(schedules) == 1
    assert schedules[0]["cron"] == "0 8 1 * *"


async def test_tool_persists_to_disk_registry(tmp_path):
    """Scheduling must survive a process restart. Verify via a fresh
    registry instance reading the same directory."""
    reg = ScheduleRegistry(base_dir=tmp_path)
    tool = ReportScheduleTool(registry=reg)
    ctx = SessionContext()
    inp = ReportScheduleInput(
        report_name="monthly_pl",
        cron="0 8 1 * *",
        var_name="pl_data",
        format="excel",
        output_path="/reports/monthly_pl.xlsx",
    )
    await tool.execute(inp, ctx)

    fresh_reg = ScheduleRegistry(base_dir=tmp_path)
    entries = fresh_reg.list()
    assert len(entries) == 1
    assert entries[0]["report_name"] == "monthly_pl"


async def test_tool_returns_next_steps_for_architect_not_executor(tmp_path):
    """Tool result must explicitly say what the user (or a downstream
    system) must do to make the schedule actually run. No silent success."""
    reg = ScheduleRegistry(base_dir=tmp_path)
    tool = ReportScheduleTool(registry=reg)
    ctx = SessionContext()
    inp = ReportScheduleInput(
        report_name="q1",
        cron="0 8 1 1 *",
        var_name="q1_data",
        format="pdf",
        output_path="/reports/q1.pdf",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error

    content = result.content
    assert "next_steps" in content
    # The next_steps must mention at least one concrete execution pathway
    # (cron, task scheduler, or workflow_deploy) — NOT just "success".
    ns = json.dumps(content["next_steps"]).lower()
    assert any(k in ns for k in ("cron", "task scheduler", "workflow_deploy", "schtasks"))


async def test_tool_honors_dry_run(tmp_path):
    """Dry-run mode must not touch the registry — matches other file-writing
    tools."""
    reg = ScheduleRegistry(base_dir=tmp_path)
    tool = ReportScheduleTool(registry=reg)
    ctx = SessionContext()
    ctx.dry_run = True
    inp = ReportScheduleInput(
        report_name="r",
        cron="* * * * *",
        var_name="v",
        format="csv",
        output_path="/tmp/r.csv",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    # Nothing persisted
    assert reg.list() == []


async def test_tool_without_registry_still_works_for_session_only_mode(tmp_path):
    """Backward compat: instantiating ReportScheduleTool() with no registry
    must still work — session-scoped only, no persistence. This preserves
    the pre-existing call pattern some tests rely on."""
    tool = ReportScheduleTool()  # no registry
    ctx = SessionContext()
    inp = ReportScheduleInput(
        report_name="r",
        cron="* * * * *",
        var_name="v",
        format="csv",
        output_path="/tmp/r.csv",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    # ctx.settings still has the entry
    assert len(ctx.settings.get("_scheduled_reports", [])) == 1
    # But nothing on disk (trivially — there's no registry)
