"""WorkflowManageTool -- lifecycle management for deployed workflows (Phase 9 Plan 03).

Covers 7 actions: list, inspect, pause, resume, rollback, retire, health_check.
All registry mutations go through WorkflowRegistry (filelock + merge semantics
from Phase 8/09-01). The tool never subprocess-execs schedulers or calls MCP
tools directly (D-02 architect-not-executor). Pause/resume/rollback return
instructional next_steps for the LLM/user to act on externally.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.types import ToolResult


class WorkflowManageInput(BaseModel):
    action: Literal[
        "list", "inspect", "pause", "resume", "rollback", "retire", "health_check"
    ]
    workflow_name: str | None = None
    target_version: int | None = None
    include_retired: bool = False


_DESCRIPTION = """\
Manage the lifecycle of deployed Yigthinker workflows. Supports 7 actions:

- list: Return all workflows with their deployment state (hides retired by default).
- inspect: Return the full manifest (all versions) for a single workflow.
- pause: Flag a workflow as paused in the registry and return an instructional
  next_step for disabling the external scheduler. Does NOT call schtasks or MCP.
- resume: Reverse of pause; returns the mirror instructional next_step.
- rollback: Atomically flip the manifest version status + registry.current_version
  pointer to an older version. Returns a next_step telling the caller to re-run
  workflow_deploy for the rolled-back version.
- retire: Mark a workflow as retired (preserved on disk, hidden from list).
- health_check: Compute overdue + failure rate for all non-retired workflows.
  Returns null fields until Phase 10 populates last_run + run_count_30d.
"""


class WorkflowManageTool:
    name = "workflow_manage"
    description = _DESCRIPTION
    input_schema = WorkflowManageInput

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry

    async def execute(
        self, input: WorkflowManageInput, ctx: SessionContext,
    ) -> ToolResult:
        try:
            if input.action == "list":
                return self._list(input)
            if input.action == "inspect":
                return self._inspect(input)
            if input.action == "pause":
                return self._pause(input)
            if input.action == "resume":
                return self._resume(input)
            if input.action == "rollback":
                return self._rollback(input)
            if input.action == "retire":
                return self._retire(input)
            if input.action == "health_check":
                return self._health_check(input)
            return ToolResult(
                tool_use_id="",
                content=f"Unknown action: {input.action}",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

    # ------------------------------------------------------------------
    # list + inspect (LCM-01, LCM-02)
    # ------------------------------------------------------------------
    def _list(self, input: WorkflowManageInput) -> ToolResult:
        index = self._registry.load_index()
        rows: list[dict[str, Any]] = []
        for name, entry in index.get("workflows", {}).items():
            if not input.include_retired and entry.get("status") == "retired":
                continue
            rows.append({
                "name": name,
                "status": entry.get("status"),
                "description": entry.get("description"),
                "target": entry.get("target"),
                "deploy_mode": entry.get("deploy_mode"),
                "schedule": entry.get("schedule"),
                "current_version": (
                    entry.get("current_version") or entry.get("latest_version")
                ),
                "latest_version": entry.get("latest_version"),
                "last_deployed": entry.get("last_deployed"),
                "last_run": entry.get("last_run"),
                "deploy_id": entry.get("deploy_id"),
            })
        return ToolResult(
            tool_use_id="",
            content={"workflows": rows, "count": len(rows)},
        )

    def _inspect(self, input: WorkflowManageInput) -> ToolResult:
        if not input.workflow_name:
            return ToolResult(
                tool_use_id="",
                content="workflow_name is required for inspect.",
                is_error=True,
            )
        index = self._registry.load_index()
        entry = index.get("workflows", {}).get(input.workflow_name)
        if entry is None:
            return ToolResult(
                tool_use_id="",
                content=f"Workflow '{input.workflow_name}' not found.",
                is_error=True,
            )
        manifest = self._registry.get_manifest(input.workflow_name)
        return ToolResult(
            tool_use_id="",
            content={
                "name": input.workflow_name,
                "registry": entry,
                "versions": manifest.get("versions", []) if manifest else [],
                "description": (
                    manifest.get("description")
                    if manifest else entry.get("description")
                ),
            },
        )

    # ------------------------------------------------------------------
    # pause + resume (LCM-03)
    # ------------------------------------------------------------------
    def _pause(self, input: WorkflowManageInput) -> ToolResult:
        return self._set_status(input, new_status="paused")

    def _resume(self, input: WorkflowManageInput) -> ToolResult:
        return self._set_status(input, new_status="active")

    def _set_status(
        self,
        input: WorkflowManageInput,
        *,
        new_status: str,
    ) -> ToolResult:
        if not input.workflow_name:
            return ToolResult(
                tool_use_id="",
                content=f"workflow_name is required for {input.action}.",
                is_error=True,
            )
        index = self._registry.load_index()
        entry = index.get("workflows", {}).get(input.workflow_name)
        if entry is None:
            return ToolResult(
                tool_use_id="",
                content=f"Workflow '{input.workflow_name}' not found.",
                is_error=True,
            )

        # Merge-based save_index: only send the fields we care about.
        self._registry.save_index({
            "workflows": {
                input.workflow_name: {
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        })

        next_step = self._build_pause_resume_next_step(
            input.workflow_name, entry, new_status,
        )

        return ToolResult(
            tool_use_id="",
            content={
                "workflow_name": input.workflow_name,
                "previous_status": entry.get("status"),
                "new_status": new_status,
                "next_step": next_step,
                "message": (
                    f"Workflow '{input.workflow_name}' registry status set to "
                    f"'{new_status}'. Follow the next_step to keep the external "
                    f"scheduler in sync."
                ),
            },
        )

    def _build_pause_resume_next_step(
        self, workflow_name: str, entry: dict, new_status: str,
    ) -> dict[str, Any]:
        """Per D-15, return instructional next_step keyed by deploy target.

        Yigthinker does NOT call schtasks or MCP tools directly.
        """
        target = entry.get("target")
        deploy_mode = entry.get("deploy_mode")
        verb = "disable" if new_status == "paused" else "enable"
        schtasks_verb = "disable" if new_status == "paused" else "enable"

        if target == "local" or deploy_mode == "local":
            return {
                "instruction": (
                    f"{'Pause' if new_status == 'paused' else 'Resume'} the "
                    f"Windows Task Scheduler entry: "
                    f"`schtasks /change /tn \"Yigthinker_{workflow_name}\" "
                    f"/{schtasks_verb}` (or `crontab -e` on Linux/macOS to "
                    f"comment/uncomment the entry)."
                ),
                "target": "local",
            }
        if target == "power_automate":
            mcp_tool = (
                "pa_pause_flow" if new_status == "paused" else "pa_resume_flow"
            )
            return {
                "instruction": (
                    f"If the yigthinker_pa_mcp MCP package is installed, call "
                    f"`{mcp_tool}` with workflow_name='{workflow_name}'. "
                    f"Otherwise open the flow in flow.microsoft.com and "
                    f"toggle it from the details page."
                ),
                "target": "power_automate",
                "suggested_mcp_tool": mcp_tool,
            }
        if target == "uipath":
            return {
                "instruction": (
                    f"If the yigthinker_mcp_uipath MCP package is installed, "
                    f"call `ui_manage_trigger` with "
                    f"workflow_name='{workflow_name}' and action='{verb}'. "
                    f"Otherwise toggle the trigger from UiPath Orchestrator."
                ),
                "target": "uipath",
                "suggested_mcp_tool": "ui_manage_trigger",
            }
        # No known target (e.g. workflow was generated but never deployed).
        return {
            "instruction": (
                f"No deploy target recorded for '{workflow_name}'. Registry "
                f"status was flipped to '{new_status}' but there is no "
                f"external scheduler to {verb}."
            ),
            "target": None,
        }

    # ------------------------------------------------------------------
    # rollback (LCM-04)
    # ------------------------------------------------------------------
    def _rollback(self, input: WorkflowManageInput) -> ToolResult:
        if not input.workflow_name:
            return ToolResult(
                tool_use_id="",
                content="workflow_name is required for rollback.",
                is_error=True,
            )
        if input.target_version is None:
            return ToolResult(
                tool_use_id="",
                content=(
                    "target_version is required for rollback (D-19: no "
                    "implicit previous-version default)."
                ),
                is_error=True,
            )

        index = self._registry.load_index()
        entry = index.get("workflows", {}).get(input.workflow_name)
        if entry is None:
            return ToolResult(
                tool_use_id="",
                content=f"Workflow '{input.workflow_name}' not found.",
                is_error=True,
            )

        manifest = self._registry.get_manifest(input.workflow_name)
        if manifest is None:
            return ToolResult(
                tool_use_id="",
                content=f"Manifest for '{input.workflow_name}' not found.",
                is_error=True,
            )

        versions = manifest.get("versions", [])
        target_entry = next(
            (v for v in versions if v["version"] == input.target_version), None,
        )
        if target_entry is None:
            return ToolResult(
                tool_use_id="",
                content=(
                    f"target_version {input.target_version} does not exist "
                    f"for '{input.workflow_name}'. Known versions: "
                    f"{[v['version'] for v in versions]}."
                ),
                is_error=True,
            )

        current_version = (
            entry.get("current_version") or entry.get("latest_version")
        )
        if input.target_version == current_version:
            return ToolResult(
                tool_use_id="",
                content=(
                    f"target_version {input.target_version} is already the "
                    f"current version for '{input.workflow_name}'. Nothing "
                    f"to roll back."
                ),
                is_error=True,
            )

        # Transactional in-memory flip, then single save_manifest +
        # save_index. Fail-fast validation above means we never write a
        # half-applied rollback.
        for v in versions:
            if v["version"] == current_version:
                v["status"] = "superseded"
            elif v["version"] == input.target_version:
                v["status"] = "active"
        manifest["versions"] = versions
        self._registry.save_manifest(input.workflow_name, manifest)

        self._registry.save_index({
            "workflows": {
                input.workflow_name: {
                    "current_version": input.target_version,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        })

        next_step = {
            "tool": "workflow_deploy",
            "args": {
                "workflow_name": input.workflow_name,
                "version": input.target_version,
                "target": entry.get("target"),
                "deploy_mode": entry.get("deploy_mode"),
                "schedule": entry.get("schedule"),
            },
            "instruction": (
                f"Registry was rolled back to v{input.target_version}. Call "
                f"workflow_deploy with the args above to push the rolled-back "
                f"artifacts to your scheduler/RPA. Yigthinker does NOT "
                f"redeploy automatically (D-17/D-18)."
            ),
        }

        return ToolResult(
            tool_use_id="",
            content={
                "workflow_name": input.workflow_name,
                "rolled_back_from": current_version,
                "rolled_back_to": input.target_version,
                "next_step": next_step,
                "message": (
                    f"Rolled '{input.workflow_name}' back from "
                    f"v{current_version} to v{input.target_version}. "
                    f"Re-deploy required."
                ),
            },
        )

    # ------------------------------------------------------------------
    # retire (LCM-05)
    # ------------------------------------------------------------------
    def _retire(self, input: WorkflowManageInput) -> ToolResult:
        if not input.workflow_name:
            return ToolResult(
                tool_use_id="",
                content="workflow_name is required for retire.",
                is_error=True,
            )
        index = self._registry.load_index()
        entry = index.get("workflows", {}).get(input.workflow_name)
        if entry is None:
            return ToolResult(
                tool_use_id="",
                content=f"Workflow '{input.workflow_name}' not found.",
                is_error=True,
            )

        manifest = self._registry.get_manifest(input.workflow_name)
        if manifest is not None:
            current_version = (
                entry.get("current_version") or entry.get("latest_version")
            )
            for v in manifest.get("versions", []):
                if (
                    v["version"] == current_version
                    and v.get("status") == "active"
                ):
                    v["status"] = "retired"
            self._registry.save_manifest(input.workflow_name, manifest)

        self._registry.save_index({
            "workflows": {
                input.workflow_name: {
                    "status": "retired",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        })

        return ToolResult(
            tool_use_id="",
            content={
                "workflow_name": input.workflow_name,
                "new_status": "retired",
                "message": (
                    f"Workflow '{input.workflow_name}' retired. Files are "
                    f"preserved at ~/.yigthinker/workflows/"
                    f"{input.workflow_name}/ but the workflow is hidden from "
                    f"list() by default. Re-running workflow_generate with "
                    f"the same name will create a new version."
                ),
            },
        )

    # ------------------------------------------------------------------
    # health_check (LCM-06)
    # ------------------------------------------------------------------
    def _health_check(self, input: WorkflowManageInput) -> ToolResult:
        # Lazy import so the tool stays importable even if croniter is
        # somehow missing. Standard install path always has it via Phase 8.
        from croniter import croniter

        index = self._registry.load_index()
        now = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        for name, entry in index.get("workflows", {}).items():
            # Retired workflows are hidden from health_check entirely (D-20).
            # Paused workflows ARE included but get overdue=False via the
            # status guard inside _health_row (D-16, per plan review note).
            if entry.get("status") == "retired":
                continue
            row = self._health_row(name, entry, now, croniter)
            rows.append(row)
        return ToolResult(
            tool_use_id="",
            content={
                "workflows": rows,
                "count": len(rows),
                "as_of": now.isoformat(),
            },
        )

    def _health_row(
        self, name: str, entry: dict, now: datetime, croniter,
    ) -> dict[str, Any]:
        alerts: list[str] = []
        schedule = entry.get("schedule")
        status = entry.get("status", "active")

        last_run_raw = entry.get("last_run")
        last_deployed_raw = entry.get("last_deployed")
        # last_deployed fallback when last_run is None (per 09-RESEARCH
        # Pattern on health_check last_deployed fallback).
        reference_raw = last_run_raw or last_deployed_raw

        overdue = False
        # Only active workflows can be overdue (D-16: paused workflows are
        # reported with overdue=False).
        if status == "active" and schedule and reference_raw:
            try:
                reference_dt = datetime.fromisoformat(reference_raw)
                if reference_dt.tzinfo is None:
                    reference_dt = reference_dt.replace(tzinfo=timezone.utc)
                if croniter.is_valid(schedule):
                    expected_prev = croniter(schedule, now).get_prev(datetime)
                    if expected_prev.tzinfo is None:
                        expected_prev = expected_prev.replace(
                            tzinfo=timezone.utc,
                        )
                    overdue = expected_prev > reference_dt
                    if overdue and last_run_raw is not None:
                        alerts.append(
                            f"Overdue: last run {last_run_raw} is older than "
                            f"expected trigger {expected_prev.isoformat()}."
                        )
                    elif overdue:
                        alerts.append(
                            f"Potentially overdue: no last_run yet; "
                            f"last_deployed {last_deployed_raw} is older "
                            f"than expected trigger "
                            f"{expected_prev.isoformat()}."
                        )
            except (ValueError, TypeError):
                alerts.append(
                    f"Could not parse schedule or timestamp for '{name}'."
                )

        run_count = entry.get("run_count_30d") or 0
        failure_count = entry.get("failure_count_30d") or 0
        failure_rate_pct: float | None
        if run_count > 0:
            failure_rate_pct = (failure_count / run_count) * 100.0
            if failure_rate_pct > 10.0:
                alerts.append(
                    f"High failure rate: {failure_rate_pct:.1f}% in last "
                    f"30 days."
                )
        else:
            # Divide-by-zero guard per D-21: no runs means no computable rate.
            failure_rate_pct = None

        return {
            "name": name,
            "status": status,
            "schedule": schedule,
            "target": entry.get("target"),
            "deploy_mode": entry.get("deploy_mode"),
            "last_deployed": last_deployed_raw,
            "last_run": last_run_raw,
            "overdue": overdue,
            "failure_rate_pct": failure_rate_pct,
            "run_count_30d": run_count,
            "failure_count_30d": failure_count,
            "alerts": alerts,
        }
