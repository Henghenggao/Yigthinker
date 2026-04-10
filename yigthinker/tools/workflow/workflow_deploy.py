"""WorkflowDeployTool - Phase 9 deployment tool (local / guided / auto modes).

Local mode (Plan 09-01): renders task_scheduler.xml + crontab.txt + setup_guide.md
and writes them to <version_dir>/local_guided/. Updates registry.json + manifest.json
with Phase 9 deploy metadata under the existing Phase 8 filelock contract.

Guided and auto modes are implemented in Plan 09-02.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from yigthinker.session import SessionContext
from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.tools.workflow.template_engine import TemplateEngine
from yigthinker.types import ToolResult

_WEEKDAY_NAMES = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]


class WorkflowDeployInput(BaseModel):
    workflow_name: str
    version: int | None = None
    target: Literal["local", "power_automate", "uipath"]
    deploy_mode: Literal["auto", "guided", "local"]
    schedule: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict)
    notify_on_complete: str | None = None


def cron_to_ts_trigger(schedule: str, start_ref: datetime) -> dict[str, Any]:
    """Parse a 5-field cron expression into Task Scheduler trigger template vars.

    Returns a dict the task_scheduler.xml.j2 template consumes. Always includes a
    next_run StartBoundary (ISO 8601). Handles four canonical shapes
    (daily / monthly-on-Nth / weekly-on-W / every-N-hours) and falls back to
    calendar_daily with needs_manual_review=True for anything exotic.

    Raises:
        ValueError: If the schedule is not a valid cron expression (from croniter).
    """
    from croniter import croniter

    # Validates the expression; raises ValueError on garbage.
    croniter(schedule)
    itr = croniter(schedule, start_ref)
    next_run = itr.get_next(datetime)

    parts = schedule.strip().split()
    if len(parts) != 5:
        return {
            "kind": "calendar_daily",
            "start_boundary": next_run.isoformat(),
            "needs_manual_review": True,
        }

    minute, hour, dom, mon, dow = parts

    # Daily: M H * * * (and every-N-hours variant)
    if dom == "*" and mon == "*" and dow == "*":
        # Every-N-hours: 0 */N * * *
        if minute == "0" and hour.startswith("*/"):
            try:
                n = int(hour[2:])
                return {
                    "kind": "calendar_hourly",
                    "interval_hours": n,
                    "start_boundary": next_run.isoformat(),
                }
            except ValueError:
                pass
        # Plain daily if hour + minute resolve to single ints
        if hour.isdigit() and minute.isdigit():
            return {
                "kind": "calendar_daily",
                "start_boundary": next_run.isoformat(),
            }

    # Monthly-on-Nth: M H D * *
    if (
        dom.isdigit()
        and mon == "*"
        and dow == "*"
        and minute.isdigit()
        and hour.isdigit()
    ):
        return {
            "kind": "calendar_monthly",
            "day_of_month": int(dom),
            "start_boundary": next_run.isoformat(),
        }

    # Weekly: M H * * W
    if (
        dom == "*"
        and mon == "*"
        and dow.isdigit()
        and minute.isdigit()
        and hour.isdigit()
    ):
        return {
            "kind": "calendar_weekly",
            "day_of_week": _WEEKDAY_NAMES[int(dow) % 7],
            "start_boundary": next_run.isoformat(),
        }

    # Fallback - unsupported shape (ranges, lists, steps on non-trivial fields)
    return {
        "kind": "calendar_daily",
        "start_boundary": next_run.isoformat(),
        "needs_manual_review": True,
    }


def _validate_credentials(credentials: dict[str, str]) -> list[str]:
    """Reject any credential value not starting with vault:// or {{ (placeholder).

    Returns a list of offending keys (empty = clean).
    """
    offenders: list[str] = []
    for key, value in credentials.items():
        if not isinstance(value, str):
            offenders.append(key)
            continue
        if not (value.startswith("vault://") or value.startswith("{{")):
            offenders.append(key)
    return offenders


def _make_deploy_id(workflow_name: str, version: int, deploy_mode: str) -> str:
    """Generate a human-debuggable deploy id per D-28."""
    ts = int(datetime.now(timezone.utc).timestamp())
    return f"{workflow_name}-v{version}-{deploy_mode}-{ts}"


class WorkflowDeployTool:
    name = "workflow_deploy"
    description = (
        "Deploy a generated workflow to a target scheduler or RPA platform. "
        "Modes: local (Task Scheduler XML + crontab), guided (paste-ready RPA "
        "bundle), auto (returns MCP tool call plan for the LLM). The tool is an "
        "architect, not an executor - it writes artifacts and metadata, never "
        "invokes schedulers or MCP tools directly."
    )
    input_schema = WorkflowDeployInput

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry
        self._engine = TemplateEngine()

    async def execute(
        self, input: WorkflowDeployInput, ctx: SessionContext,
    ) -> ToolResult:
        try:
            return await self._do_execute(input, ctx)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

    async def _do_execute(
        self, input: WorkflowDeployInput, ctx: SessionContext,
    ) -> ToolResult:
        # 1. Validate target/mode combo (D-23)
        if input.target == "local" and input.deploy_mode != "local":
            return ToolResult(
                tool_use_id="",
                content=(
                    f"target='local' requires deploy_mode='local' "
                    f"(got deploy_mode='{input.deploy_mode}')."
                ),
                is_error=True,
            )

        # 2. Validate credentials are vault:// refs only (Pitfall 2)
        bad = _validate_credentials(input.credentials)
        if bad:
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Credentials must be vault:// refs only. Offending keys: {bad}"
                ),
                is_error=True,
            )

        # 3. Load registry entry + manifest (both via lazy defaults)
        index = self._registry.load_index()
        if input.workflow_name not in index.get("workflows", {}):
            return ToolResult(
                tool_use_id="",
                content=f"Workflow '{input.workflow_name}' not found in registry.",
                is_error=True,
            )
        entry = index["workflows"][input.workflow_name]
        manifest = self._registry.get_manifest(input.workflow_name)
        if manifest is None:
            return ToolResult(
                tool_use_id="",
                content=f"Manifest for '{input.workflow_name}' missing.",
                is_error=True,
            )

        # 4. Resolve version (explicit -> current_version -> latest_version)
        version = input.version
        if version is None:
            version = entry.get("current_version") or entry["latest_version"]
        version_dir = (
            self._registry._base_dir / input.workflow_name / f"v{version}"
        )
        if not version_dir.exists():
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Version directory missing: {version_dir}. "
                    f"Generate v{version} via workflow_generate first."
                ),
                is_error=True,
            )

        # 5. Validate schedule (fail-fast)
        schedule = input.schedule or entry.get("schedule")
        if schedule is None:
            return ToolResult(
                tool_use_id="",
                content="schedule is required for local deploy mode.",
                is_error=True,
            )
        try:
            from croniter import croniter
            croniter(schedule)
        except (ValueError, KeyError) as exc:
            return ToolResult(
                tool_use_id="",
                content=f"Invalid cron expression '{schedule}': {exc}",
                is_error=True,
            )

        # 6. Dispatch by mode
        if input.deploy_mode == "local":
            return self._deploy_local(input, version, version_dir, schedule)

        # Guided + auto delegated to Plan 09-02.
        return ToolResult(
            tool_use_id="",
            content=(
                f"deploy_mode='{input.deploy_mode}' is not yet implemented "
                f"in Plan 09-01 - see Plan 09-02."
            ),
            is_error=True,
        )

    def _deploy_local(
        self,
        input: WorkflowDeployInput,
        version: int,
        version_dir: Path,
        schedule: str,
    ) -> ToolResult:
        local_dir = version_dir / "local_guided"
        local_dir.mkdir(parents=True, exist_ok=True)

        # Windows working dir uses native separators; POSIX uses forward slashes.
        # The XML only runs on Windows, the crontab only runs on POSIX.
        working_dir_windows = str(version_dir)
        working_dir_posix = version_dir.as_posix()
        # python_exe: native absolute path for Windows XML context, forward-
        # slashed variant for the POSIX crontab context (Pitfall 7). Users on
        # a non-Windows host will edit the crontab to point at their real
        # python3; the posix-slashed sys.executable is a placeholder that at
        # least doesn't contain backslashes.
        python_exe_windows = sys.executable
        python_exe_posix = Path(sys.executable).as_posix()

        now = datetime.now(timezone.utc)
        trigger = cron_to_ts_trigger(schedule, now)

        xml_ctx = {
            "workflow_name": input.workflow_name,
            "description": (
                input.notify_on_complete
                or f"Yigthinker workflow {input.workflow_name} v{version}"
            ),
            "schedule": schedule,
            "python_exe": python_exe_windows,
            "working_dir": working_dir_windows,
            "working_dir_windows": working_dir_windows,
            "working_dir_posix": working_dir_posix,
            "registration_date": now.isoformat(),
            "trigger": trigger,
        }
        cron_ctx = {
            **xml_ctx,
            "python_exe": python_exe_posix,
        }
        guide_ctx = xml_ctx  # guide references both working_dir_* keys

        xml_rendered = self._engine.render_text(
            "local/task_scheduler.xml.j2", xml_ctx,
        )
        cron_rendered = self._engine.render_text(
            "local/crontab.txt.j2", cron_ctx,
        )
        guide_rendered = self._engine.render_text(
            "local/setup_guide.md.j2", guide_ctx,
        )

        (local_dir / "task_scheduler.xml").write_text(xml_rendered, encoding="utf-8")
        (local_dir / "crontab.txt").write_text(cron_rendered, encoding="utf-8")
        (local_dir / "setup_guide.md").write_text(guide_rendered, encoding="utf-8")

        # Registry + manifest write-back (D-14)
        deploy_id = _make_deploy_id(input.workflow_name, version, "local")
        last_deployed = now.isoformat()

        # Merge-based index patch - save_index merges workflows dicts per-entry
        # under the filelock, so no TOCTOU read-before-write.
        index_patch = {
            "workflows": {
                input.workflow_name: {
                    "target": "local",
                    "deploy_mode": "local",
                    "schedule": schedule,
                    "last_deployed": last_deployed,
                    "deploy_id": deploy_id,
                    "current_version": version,
                }
            }
        }
        self._registry.save_index(index_patch)

        # Manifest: update the matching version entry
        manifest = self._registry.get_manifest(input.workflow_name)
        # manifest is not None (we verified above)
        assert manifest is not None
        for v in manifest["versions"]:
            if v["version"] == version:
                v["deployed_to"] = "local"
                v["deploy_mode"] = "local"
                v["deploy_id"] = deploy_id
                v["status"] = "active"
                break
        self._registry.save_manifest(input.workflow_name, manifest)

        return ToolResult(
            tool_use_id="",
            content={
                "mode": "local",
                "target": "local",
                "workflow_name": input.workflow_name,
                "version": version,
                "deploy_id": deploy_id,
                "artifacts_ready": {
                    "task_scheduler.xml": str(local_dir / "task_scheduler.xml"),
                    "crontab.txt": str(local_dir / "crontab.txt"),
                    "setup_guide.md": str(local_dir / "setup_guide.md"),
                },
                "trigger_kind": trigger["kind"],
                "needs_manual_review": trigger.get("needs_manual_review", False),
                "message": (
                    f"Local deploy artifacts ready in {local_dir}. "
                    f"Install via Windows Task Scheduler (schtasks /create /xml "
                    f"task_scheduler.xml) or POSIX cron (crontab crontab.txt). "
                    f"See setup_guide.md for step-by-step instructions."
                ),
            },
        )
