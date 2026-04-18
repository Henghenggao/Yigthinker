"""Report scheduling tool + file-backed schedule registry.

Historical note (2026-04-17): pre-durable `ReportScheduleTool` stored entries
only in `ctx.settings["_scheduled_reports"]` — lost on restart — and returned
a flat success result with no indication of how to actually run the
schedule. TODOs.md flagged it as "returns success for work that does not
survive restarts."

This module now:

- Persists schedules via `ScheduleRegistry` (file-backed JSON at
  `~/.yigthinker/scheduled_reports.json`, atomic writes via filelock).
- Keeps `ctx.settings["_scheduled_reports"]` populated for the in-session
  `/schedule` CLI command (backward compat).
- Returns architect-not-executor `next_steps` telling the caller how to
  wire the schedule into cron / Windows Task Scheduler / or a future
  workflow-tool integration — the tool DOES NOT itself execute schedules.

Follow-up (out of scope for this pass): APScheduler in-process executor or
`workflow_deploy` integration so `report_schedule` becomes sugar over the
existing workflow system.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

try:
    from filelock import FileLock
except ImportError:  # pragma: no cover — filelock is a core dep
    FileLock = None  # type: ignore[misc,assignment]

from yigthinker.session import SessionContext
from yigthinker.types import DryRunReceipt, ToolResult


_SCHEDULE_FILE_VERSION = 1


def _default_base_dir() -> Path:
    """Default location: ~/.yigthinker/ (same root as other durable stores)."""
    return Path.home() / ".yigthinker"


class ScheduleRegistry:
    """File-backed store for scheduled report entries.

    On-disk layout (`<base_dir>/scheduled_reports.json`):

        {
          "version": 1,
          "schedules": [
            {"schedule_id": "...", "cron": "...", ...},
            ...
          ]
        }

    Atomic writes via filelock + `os.replace` (same pattern as
    WorkflowRegistry). The lock file is `<base_dir>/.scheduled_reports.lock`.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else _default_base_dir()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._base_dir / "scheduled_reports.json"
        self._lock_path = self._base_dir / ".scheduled_reports.lock"

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"version": _SCHEDULE_FILE_VERSION, "schedules": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": _SCHEDULE_FILE_VERSION, "schedules": []}
        # Shape-check: a corrupt file (e.g. truncated) falls back to empty
        # rather than crashing — better than silent data loss on next write.
        if not isinstance(data, dict) or "schedules" not in data:
            return {"version": _SCHEDULE_FILE_VERSION, "schedules": []}
        data.setdefault("version", _SCHEDULE_FILE_VERSION)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        """Atomic write: tempfile in same dir + os.replace."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._base_dir,
            prefix=".scheduled_reports.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self._path)

    def list(self) -> list[dict[str, Any]]:
        """Return current schedule entries (possibly empty)."""
        lock_cm = FileLock(str(self._lock_path)) if FileLock else _NullLock()
        with lock_cm:
            return self._load().get("schedules", [])

    def add(self, entry: dict[str, Any]) -> None:
        """Append an entry. Holds the filelock across read-modify-write."""
        lock_cm = FileLock(str(self._lock_path)) if FileLock else _NullLock()
        with lock_cm:
            data = self._load()
            data["schedules"].append(entry)
            self._save(data)

    def remove(self, schedule_id: str) -> bool:
        """Drop entry by schedule_id. Returns True if removed, False if absent."""
        lock_cm = FileLock(str(self._lock_path)) if FileLock else _NullLock()
        with lock_cm:
            data = self._load()
            before = len(data["schedules"])
            data["schedules"] = [
                e for e in data["schedules"]
                if e.get("schedule_id") != schedule_id
            ]
            if len(data["schedules"]) == before:
                return False
            self._save(data)
            return True


class _NullLock:
    """No-op context manager used when filelock is unavailable (testing)."""

    def __enter__(self) -> "_NullLock":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class ReportScheduleInput(BaseModel):
    report_name: str
    cron: str
    var_name: str
    format: str = "excel"
    output_path: str


class ReportScheduleTool:
    name = "report_schedule"
    description = (
        "Register a report for scheduled generation. Persists the entry to "
        "~/.yigthinker/scheduled_reports.json (survives restart) and returns "
        "architect-not-executor next_steps: a cron line + a Windows Task "
        "Scheduler hint. The tool does NOT run the schedule — the caller "
        "installs the cron line or uses workflow_deploy for a full "
        "automation hand-off."
    )
    input_schema = ReportScheduleInput

    def __init__(self, registry: ScheduleRegistry | None = None) -> None:
        """Construct the tool.

        If ``registry`` is None, the tool runs session-only (entries live in
        ``ctx.settings["_scheduled_reports"]`` but do NOT persist to disk).
        Callers that care about durability must pass an explicit registry.
        """
        self._registry = registry

    async def execute(
        self, input: ReportScheduleInput, ctx: SessionContext,
    ) -> ToolResult:
        if getattr(ctx, "dry_run", False):
            return ToolResult(
                tool_use_id="",
                content=DryRunReceipt(
                    tool_name=self.name,
                    summary=(
                        f"Would register schedule '{input.report_name}' "
                        f"cron='{input.cron}' → {input.output_path}"
                    ),
                    details={"input": input.model_dump()},
                ),
            )

        schedule_id = str(uuid.uuid4())[:8]
        entry = {
            "schedule_id": schedule_id,
            "report_name": input.report_name,
            "cron": input.cron,
            "var_name": input.var_name,
            "format": input.format,
            "output_path": input.output_path,
        }

        # In-session view (backward compat with /schedule CLI command)
        ctx.settings.setdefault("_scheduled_reports", []).append(entry)

        # Durable persistence — only if a registry was injected.
        if self._registry is not None:
            self._registry.add(entry)

        next_steps = self._build_next_steps(input, schedule_id)

        return ToolResult(
            tool_use_id="",
            content={
                "schedule_id": schedule_id,
                "cron": input.cron,
                "report_name": input.report_name,
                "persisted": self._registry is not None,
                "next_steps": next_steps,
            },
        )

    def _build_next_steps(
        self, input: ReportScheduleInput, schedule_id: str,
    ) -> dict[str, Any]:
        """Architect-not-executor hand-off instructions.

        Returns both POSIX cron + Windows Task Scheduler recipes so the
        caller (LLM or human) can pick the right one for their environment.
        The scheduled command assumes the user has a Yigthinker CLI on
        PATH that can re-run a report by schedule_id — we surface the
        shape, we don't force a particular command binary.
        """
        cmd_hint = (
            f"yigthinker run-scheduled --id {schedule_id}"
            f"  # placeholder: wire to your preferred executor"
        )
        return {
            "posix_cron": f"{input.cron} {cmd_hint}",
            "windows_task_scheduler": (
                f"schtasks /create /tn yigthinker_{input.report_name} "
                f"/sc {_cron_to_schtasks_hint(input.cron)} /tr \"{cmd_hint}\""
            ),
            "workflow_deploy_hint": (
                "For a full Yigthinker hand-off with self-healing callback, "
                "use workflow_generate + workflow_deploy instead of this "
                "tool. report_schedule is for lightweight pointer-style "
                "registration only."
            ),
            "note": (
                "This tool does not run the schedule — it records it. "
                "Install the cron line or the scheduled task yourself, or "
                "feed the entry to your orchestrator."
            ),
        }


def _cron_to_schtasks_hint(cron: str) -> str:
    """Best-effort translation of a 5-field cron string to a schtasks
    frequency keyword. Intentionally conservative — unclear shapes fall
    back to 'MINUTE' + an instruction to check the generated command."""
    parts = cron.split()
    if len(parts) != 5:
        return "MINUTE"
    minute, hour, dom, month, dow = parts
    if dom != "*" and dom != "?" and month == "*" and dow == "*":
        return "MONTHLY"
    if dow != "*" and dow != "?" and dom == "*" and month == "*":
        return "WEEKLY"
    if dom == "*" and month == "*" and dow == "*" and hour != "*":
        return "DAILY"
    if all(p == "*" for p in (hour, dom, month, dow)):
        return "MINUTE"
    return "MINUTE"
