"""WorkflowDeployTool - Phase 9 deployment tool (local / guided / auto modes).

Local mode (Plan 09-01): renders task_scheduler.xml + crontab.txt + setup_guide.md
and writes them to <version_dir>/local_guided/. Updates registry.json + manifest.json
with Phase 9 deploy metadata under the existing Phase 8 filelock contract.

Guided mode (Plan 09-02): renders a paste-ready bundle ZIP (flow_import.zip for
Power Automate, process_package.zip for UiPath) plus a target-specific
setup_guide.md into <version_dir>/<target>_guided/. Uses pa_bundle +
uipath_bundle helpers.

Auto mode (Plan 09-02): informational-only. Uses mcp_detection.check_mcp_installed
to see whether the expected MCP package is importable (via importlib.util.find_spec,
never an actual import). On success, builds the guided bundle as a hand-off
artifact and returns structured next_steps naming the MCP tool + bundle path.
On missing package, returns is_error=True with pip extras hint. Per D-02 the
tool NEVER calls MCP tools directly or subprocess-execs anything.
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


def cron_to_pa_recurrence(cron_expr: str) -> dict[str, Any]:
    """Translate a 5-field cron expression to PA Recurrence {frequency, interval}.

    Per Phase 9 Research Pattern 7, maps the four canonical cron shapes:

      "0 8 * * *"    -> frequency=Day,   interval=1
      "0 8 * * 1"    -> frequency=Week,  interval=1
      "0 8 5 * *"    -> frequency=Month, interval=1
      "0 */4 * * *"  -> frequency=Hour,  interval=4

    For anything we cannot map cleanly (ranges, lists, steps on non-trivial
    fields) we fall back to Day/1 and set ``needs_manual_review=True`` - the
    setup_guide tells the user to fix it in flow.microsoft.com after import.

    Raises:
        ValueError: if the cron expression is not valid per croniter.
    """
    from croniter import croniter

    # croniter() raises ValueError on garbage; propagate to caller.
    croniter(cron_expr)

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return {
            "frequency": "Day",
            "interval": 1,
            "needs_manual_review": True,
        }
    minute, hour, dom, mon, dow = parts

    # Hour: "0 */N * * *"
    if (
        dom == "*"
        and mon == "*"
        and dow == "*"
        and hour.startswith("*/")
    ):
        try:
            n = int(hour[2:])
            return {
                "frequency": "Hour",
                "interval": n,
                "needs_manual_review": False,
            }
        except ValueError:
            pass

    # Day: plain "M H * * *" (no step / range in hour)
    if (
        dom == "*"
        and mon == "*"
        and dow == "*"
        and "/" not in hour
        and "-" not in hour
        and "," not in hour
    ):
        return {
            "frequency": "Day",
            "interval": 1,
            "needs_manual_review": False,
        }

    # Week: "M H * * D" with single weekday digit
    if (
        dom == "*"
        and mon == "*"
        and dow != "*"
        and "/" not in dow
        and "-" not in dow
        and "," not in dow
    ):
        return {
            "frequency": "Week",
            "interval": 1,
            "needs_manual_review": False,
        }

    # Month: "M H D * *" with single day-of-month digit
    if (
        dom != "*"
        and mon == "*"
        and dow == "*"
        and "/" not in dom
        and "-" not in dom
        and "," not in dom
    ):
        return {
            "frequency": "Month",
            "interval": 1,
            "needs_manual_review": False,
        }

    # Fallback - exotic shape; user must fix after import.
    return {
        "frequency": "Day",
        "interval": 1,
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
        if input.deploy_mode == "guided":
            return self._dispatch_guided(
                input, version, version_dir, schedule,
            )
        if input.deploy_mode == "auto":
            return await self._dispatch_auto(
                input, version, version_dir, schedule,
            )

        # Unreachable - Pydantic Literal validation guards the schema,
        # but keep an explicit fallback for forward compatibility.
        return ToolResult(
            tool_use_id="",
            content=f"Unknown deploy_mode: {input.deploy_mode}",
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

    # ------------------------------------------------------------------
    # Plan 09-02: guided dispatcher
    # ------------------------------------------------------------------

    def _dispatch_guided(
        self,
        input: WorkflowDeployInput,
        version: int,
        version_dir: Path,
        schedule: str,
    ) -> ToolResult:
        """Render a paste-ready bundle ZIP for a PA or UiPath target.

        Writes <version_dir>/<target>_guided/<bundle>.zip + setup_guide.md
        and updates registry.json + manifest.json per D-11/D-12.

        Returns an is_error ToolResult if ``target == "local"`` — that
        combination is rejected upstream in ``_do_execute`` via the
        target/mode combo validation, but we guard it here too for
        defense-in-depth.
        """
        from yigthinker.tools.workflow.pa_bundle import build_pa_bundle
        from yigthinker.tools.workflow.uipath_bundle import build_uipath_bundle

        if input.target == "local":
            return ToolResult(
                tool_use_id="",
                content=(
                    "target='local' is only valid with deploy_mode='local' "
                    "(see D-23). Use deploy_mode='local' for OS scheduler "
                    "bundles."
                ),
                is_error=True,
            )

        target_dir_name = (
            "power_automate_guided"
            if input.target == "power_automate"
            else "uipath_guided"
        )
        output_dir = version_dir / target_dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        registration_date = now.isoformat()
        deploy_id = _make_deploy_id(
            input.workflow_name, version, "guided",
        )

        # Pull description from the manifest (set by workflow_generate).
        manifest = self._registry.get_manifest(input.workflow_name)
        assert manifest is not None  # _do_execute already verified
        description = (
            manifest.get("description")
            or input.notify_on_complete
            or f"Yigthinker workflow {input.workflow_name} v{version}"
        )
        display_name = f"Yigthinker: {input.workflow_name}"

        if input.target == "power_automate":
            recurrence = cron_to_pa_recurrence(schedule)
            tpl_vars: dict[str, Any] = {
                "workflow_name": input.workflow_name,
                "display_name": display_name,
                "description": description,
                "cron_expression": schedule,
                "recurrence_frequency": recurrence["frequency"],
                "recurrence_interval": recurrence["interval"],
                "registration_date": registration_date,
            }
            bundle_path = build_pa_bundle(
                workflow_name=input.workflow_name,
                variables=tpl_vars,
                engine=self._engine,
                output_dir=output_dir,
            )
            setup_guide = self._engine.render_text(
                "pa/setup_guide.md.j2", tpl_vars,
            )
            needs_manual_review = bool(
                recurrence.get("needs_manual_review"),
            )
        else:  # uipath
            tpl_vars = {
                "workflow_name": input.workflow_name,
                "display_name": display_name,
                "description": description,
                "python_exe": sys.executable,
                "registration_date": registration_date,
            }
            bundle_path = build_uipath_bundle(
                workflow_name=input.workflow_name,
                variables=tpl_vars,
                engine=self._engine,
                output_dir=output_dir,
            )
            setup_guide = self._engine.render_text(
                "uipath/setup_guide.md.j2", tpl_vars,
            )
            # UiPath always needs the user to wire a Python Scope, but that's
            # documented in the setup_guide and not a cron translation gap.
            needs_manual_review = False

        setup_path = output_dir / "setup_guide.md"
        setup_path.write_text(setup_guide, encoding="utf-8")

        # Registry writeback (D-11 / D-14)
        self._registry.save_index(
            {
                "workflows": {
                    input.workflow_name: {
                        "target": input.target,
                        "deploy_mode": "guided",
                        "schedule": schedule,
                        "last_deployed": registration_date,
                        "deploy_id": deploy_id,
                        "current_version": version,
                    }
                }
            }
        )

        # Manifest writeback (D-12)
        updated = self._registry.get_manifest(input.workflow_name)
        assert updated is not None
        for v in updated["versions"]:
            if v["version"] == version:
                v["deployed_to"] = input.target
                v["deploy_mode"] = "guided"
                v["deploy_id"] = deploy_id
                v["status"] = "active"
                break
        self._registry.save_manifest(input.workflow_name, updated)

        return ToolResult(
            tool_use_id="",
            content={
                "mode": "guided",
                "target": input.target,
                "workflow_name": input.workflow_name,
                "version": version,
                "deploy_id": deploy_id,
                "artifacts_ready": {
                    "bundle": str(bundle_path),
                    "setup_guide": str(setup_path),
                },
                "needs_manual_review": needs_manual_review,
                "message": (
                    f"Guided bundle ready at {bundle_path}. "
                    f"Open {setup_path} for step-by-step import instructions."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Plan 09-02: auto dispatcher (informational, never calls MCP)
    # ------------------------------------------------------------------

    async def _dispatch_auto(
        self,
        input: WorkflowDeployInput,
        version: int,
        version_dir: Path,
        schedule: str,
    ) -> ToolResult:
        """Inspect MCP installation and return instructional next_steps.

        Per D-02 this method NEVER calls the MCP. It only tells the LLM
        whether the MCP package is importable and what tool to invoke.
        Detection uses importlib.util.find_spec via mcp_detection.check_mcp_installed
        which never imports the module.

        On success, we also build the guided bundle as a hand-off artifact
        (so the LLM has a concrete bundle_path to pass to the MCP tool),
        then rewrite the registry row to deploy_mode=auto and status
        pending_auto_deploy.
        """
        from yigthinker.tools.workflow import mcp_detection

        if input.target == "local":
            return ToolResult(
                tool_use_id="",
                content=(
                    "target='local' is only valid with deploy_mode='local' "
                    "(see D-23). Auto mode requires a cloud target."
                ),
                is_error=True,
            )

        mcp_package = mcp_detection.MCP_PACKAGE_MAP[input.target]
        tool_info = mcp_detection.MCP_TOOL_MAP[input.target]

        if not mcp_detection.check_mcp_installed(mcp_package):
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Auto mode requires the {mcp_package} package. "
                    f"Install with '{tool_info['install_hint']}' or use "
                    f"deploy_mode='guided' for a paste-ready bundle "
                    f"instead."
                ),
                is_error=True,
            )

        # MCP is present — build the bundle via the guided dispatcher so
        # the LLM has something concrete to hand to the MCP tool. This
        # also writes the guided entry to the registry; we flip it to
        # auto/pending_auto_deploy immediately after.
        guided_result = self._dispatch_guided(
            input, version, version_dir, schedule,
        )
        if guided_result.is_error:
            return guided_result

        assert isinstance(guided_result.content, dict)
        bundle_path = guided_result.content["artifacts_ready"]["bundle"]
        setup_guide_path = guided_result.content["artifacts_ready"][
            "setup_guide"
        ]

        now = datetime.now(timezone.utc)
        registration_date = now.isoformat()
        deploy_id_auto = _make_deploy_id(
            input.workflow_name, version, "auto",
        )

        # Flip the registry row to auto / pending_auto_deploy.
        self._registry.save_index(
            {
                "workflows": {
                    input.workflow_name: {
                        "target": input.target,
                        "deploy_mode": "auto",
                        "schedule": schedule,
                        "last_deployed": registration_date,
                        "deploy_id": deploy_id_auto,
                        "current_version": version,
                    }
                }
            }
        )
        updated = self._registry.get_manifest(input.workflow_name)
        assert updated is not None
        for v in updated["versions"]:
            if v["version"] == version:
                v["deploy_mode"] = "auto"
                v["deploy_id"] = deploy_id_auto
                v["status"] = "pending_auto_deploy"
                break
        self._registry.save_manifest(input.workflow_name, updated)

        return ToolResult(
            tool_use_id="",
            content={
                "mode": "auto",
                "target": input.target,
                "workflow_name": input.workflow_name,
                "version": version,
                "deploy_id": deploy_id_auto,
                "mcp_installed": True,
                "mcp_package": mcp_package,
                "artifacts_ready": {
                    "bundle": bundle_path,
                    "setup_guide": setup_guide_path,
                },
                "next_steps": {
                    "suggested_tool": tool_info["suggested_tool"],
                    "mcp_package": mcp_package,
                    "bundle_path": bundle_path,
                    "instructions": (
                        f"The {mcp_package} MCP package is installed. To "
                        f"complete the deploy, ask Claude to call the "
                        f"'{tool_info['suggested_tool']}' tool (exposed by "
                        f"the MCP server) with bundle_path='{bundle_path}' "
                        f"and any auth credentials required by your "
                        f"environment. Yigthinker will NOT call this tool "
                        f"directly (per D-02 Yigthinker generates, never "
                        f"executes deploys)."
                    ),
                },
                "message": (
                    f"Auto mode ready. MCP package {mcp_package} detected; "
                    f"bundle staged at {bundle_path}. Status set to "
                    f"pending_auto_deploy until the MCP tool confirms."
                ),
            },
        )
