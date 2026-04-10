"""Tests for WorkflowManageTool (Phase 9 Plan 03).

Covers all 7 actions: list, inspect, pause, resume, rollback, retire, health_check.
Uses WorkflowRegistry(base_dir=tmp_path) fixture -- no real Jinja rendering, no subprocess.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.tools.workflow.workflow_manage import (
    WorkflowManageInput,
    WorkflowManageTool,
)


@pytest.fixture
def registry(tmp_path: Path) -> WorkflowRegistry:
    return WorkflowRegistry(base_dir=tmp_path)


@pytest.fixture
def ctx() -> SessionContext:
    # Phase 8/09-01 pattern: zero-arg SessionContext() uses default_factory for all
    # fields including vars=VarRegistry(). workflow_manage never reads ctx.vars, but
    # the real SessionContext has a VarRegistry (not None), so match the real shape.
    return SessionContext()


@pytest.fixture
def tool(registry: WorkflowRegistry) -> WorkflowManageTool:
    return WorkflowManageTool(registry=registry)


def _seed_workflow(
    registry: WorkflowRegistry,
    name: str,
    *,
    target: str = "power_automate",
    deploy_mode: str = "guided",
    schedule: str = "0 8 * * *",
    current_version: int = 2,
    latest_version: int = 2,
    status: str = "active",
    last_deployed: str | None = None,
    last_run: str | None = None,
    run_count_30d: int = 0,
    failure_count_30d: int = 0,
) -> None:
    """Seed a workflow directly into the registry for testing."""
    now = datetime.now(timezone.utc).isoformat()
    registry.save_index({
        "workflows": {
            name: {
                "status": status,
                "latest_version": latest_version,
                "current_version": current_version,
                "description": f"Seeded {name}",
                "created_at": now,
                "updated_at": now,
                "target": target,
                "deploy_mode": deploy_mode,
                "schedule": schedule,
                "last_deployed": last_deployed or now,
                "last_run": last_run,
                "last_run_status": "success" if last_run else None,
                "failure_count_30d": failure_count_30d,
                "run_count_30d": run_count_30d,
                "deploy_id": f"{name}-v{current_version}-{deploy_mode}-1700000000",
            }
        }
    })

    versions = []
    for v in range(1, latest_version + 1):
        versions.append({
            "version": v,
            "created_at": now,
            "status": "active" if v == current_version else "superseded",
            "deployed_to": target,
            "deploy_mode": deploy_mode,
            "deploy_id": f"{name}-v{v}-{deploy_mode}-17000000{v:02d}",
        })
    registry.save_manifest(
        name,
        {"name": name, "description": f"Seeded {name}", "versions": versions},
    )


# ---------------------------------------------------------------------------
# list + inspect (LCM-01, LCM-02)
# ---------------------------------------------------------------------------
class TestWorkflowManageList:
    async def test_list_and_inspect(self, tool, registry, ctx):
        """Happy-path list returns seeded workflows; inspect returns full manifest."""
        _seed_workflow(registry, "wf_alpha")
        _seed_workflow(registry, "wf_beta", target="local", deploy_mode="local")

        list_result = await tool.execute(WorkflowManageInput(action="list"), ctx)
        assert list_result.is_error is False
        assert "workflows" in list_result.content
        names = {w["name"] for w in list_result.content["workflows"]}
        assert names == {"wf_alpha", "wf_beta"}

        inspect_result = await tool.execute(
            WorkflowManageInput(action="inspect", workflow_name="wf_alpha"),
            ctx,
        )
        assert inspect_result.is_error is False
        assert inspect_result.content["name"] == "wf_alpha"
        assert len(inspect_result.content["versions"]) == 2
        assert inspect_result.content["registry"]["target"] == "power_automate"

    async def test_list_hides_retired_by_default(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_active", status="active")
        _seed_workflow(registry, "wf_retired", status="retired")
        result = await tool.execute(WorkflowManageInput(action="list"), ctx)
        names = {w["name"] for w in result.content["workflows"]}
        assert "wf_active" in names
        assert "wf_retired" not in names

    async def test_list_includes_retired_when_flag_set(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_active", status="active")
        _seed_workflow(registry, "wf_retired", status="retired")
        result = await tool.execute(
            WorkflowManageInput(action="list", include_retired=True), ctx,
        )
        names = {w["name"] for w in result.content["workflows"]}
        assert {"wf_active", "wf_retired"}.issubset(names)

    async def test_inspect_unknown_workflow_errors(self, tool, ctx):
        result = await tool.execute(
            WorkflowManageInput(action="inspect", workflow_name="nope"), ctx,
        )
        assert result.is_error is True
        assert "not found" in str(result.content).lower()


# ---------------------------------------------------------------------------
# pause + resume (LCM-03)
# ---------------------------------------------------------------------------
class TestWorkflowManagePause:
    async def test_pause_resume(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_p")
        pause = await tool.execute(
            WorkflowManageInput(action="pause", workflow_name="wf_p"), ctx,
        )
        assert pause.is_error is False
        assert registry.load_index()["workflows"]["wf_p"]["status"] == "paused"
        assert "next_step" in pause.content

        resume = await tool.execute(
            WorkflowManageInput(action="resume", workflow_name="wf_p"), ctx,
        )
        assert resume.is_error is False
        assert registry.load_index()["workflows"]["wf_p"]["status"] == "active"
        assert "next_step" in resume.content

    async def test_pause_returns_next_step_local(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_local", target="local", deploy_mode="local")
        result = await tool.execute(
            WorkflowManageInput(action="pause", workflow_name="wf_local"), ctx,
        )
        assert "schtasks" in str(result.content["next_step"]).lower()

    async def test_pause_returns_next_step_power_automate(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_pa")
        result = await tool.execute(
            WorkflowManageInput(action="pause", workflow_name="wf_pa"), ctx,
        )
        ns = str(result.content["next_step"]).lower()
        assert "pa_pause_flow" in ns or "power_automate" in ns

    async def test_pause_requires_workflow_name(self, tool, ctx):
        result = await tool.execute(WorkflowManageInput(action="pause"), ctx)
        assert result.is_error is True


# ---------------------------------------------------------------------------
# rollback (LCM-04)
# ---------------------------------------------------------------------------
class TestWorkflowManageRollback:
    async def test_rollback(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_rb", latest_version=2, current_version=2)
        result = await tool.execute(
            WorkflowManageInput(
                action="rollback", workflow_name="wf_rb", target_version=1,
            ),
            ctx,
        )
        assert result.is_error is False

        # Registry current_version pointer flipped to 1
        row = registry.load_index()["workflows"]["wf_rb"]
        assert row["current_version"] == 1

        # Manifest version statuses flipped
        manifest = registry.get_manifest("wf_rb")
        v1 = next(v for v in manifest["versions"] if v["version"] == 1)
        v2 = next(v for v in manifest["versions"] if v["version"] == 2)
        assert v1["status"] == "active"
        assert v2["status"] == "superseded"

        # Next-step payload suggests workflow_deploy
        ns = result.content["next_step"]
        assert ns["tool"] == "workflow_deploy"
        assert ns["args"]["workflow_name"] == "wf_rb"
        assert ns["args"]["version"] == 1

    async def test_rollback_requires_target_version(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_rb2")
        result = await tool.execute(
            WorkflowManageInput(action="rollback", workflow_name="wf_rb2"), ctx,
        )
        assert result.is_error is True
        assert "target_version" in str(result.content).lower()

    async def test_rollback_unknown_target_version_errors(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_rb3", latest_version=2)
        result = await tool.execute(
            WorkflowManageInput(
                action="rollback", workflow_name="wf_rb3", target_version=99,
            ),
            ctx,
        )
        assert result.is_error is True

    async def test_rollback_same_version_is_noop_or_errors(
        self, tool, registry, ctx,
    ):
        _seed_workflow(registry, "wf_rb4", latest_version=2, current_version=2)
        result = await tool.execute(
            WorkflowManageInput(
                action="rollback", workflow_name="wf_rb4", target_version=2,
            ),
            ctx,
        )
        # Deterministic choice: rolling back to the currently-active version
        # returns is_error=True (per plan D-17/D-18 discussion).
        assert result.is_error is True


# ---------------------------------------------------------------------------
# retire (LCM-05)
# ---------------------------------------------------------------------------
class TestWorkflowManageRetire:
    async def test_retire(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_ret")
        result = await tool.execute(
            WorkflowManageInput(action="retire", workflow_name="wf_ret"), ctx,
        )
        assert result.is_error is False

        row = registry.load_index()["workflows"]["wf_ret"]
        assert row["status"] == "retired"

        manifest = registry.get_manifest("wf_ret")
        # No "active" versions after retire -- the previously active one is
        # now retired.
        assert all(
            v["status"] in {"retired", "superseded"}
            for v in manifest["versions"]
        )
        retired_versions = [
            v for v in manifest["versions"] if v["status"] == "retired"
        ]
        assert len(retired_versions) == 1

    async def test_retire_hides_from_list(self, tool, registry, ctx):
        _seed_workflow(registry, "wf_ret2")
        await tool.execute(
            WorkflowManageInput(action="retire", workflow_name="wf_ret2"), ctx,
        )
        listing = await tool.execute(WorkflowManageInput(action="list"), ctx)
        names = {w["name"] for w in listing.content["workflows"]}
        assert "wf_ret2" not in names

    async def test_retire_unknown_workflow_errors(self, tool, ctx):
        result = await tool.execute(
            WorkflowManageInput(action="retire", workflow_name="nope"), ctx,
        )
        assert result.is_error is True


# ---------------------------------------------------------------------------
# health_check (LCM-06)
# ---------------------------------------------------------------------------
class TestWorkflowManageHealthCheck:
    async def test_health_check_with_empty_data(self, tool, registry, ctx):
        """No last_run + no run_count -- tool must not crash; failure_rate_pct=None."""
        now = datetime.now(timezone.utc)
        # last_deployed is 2 hours ago; schedule is daily 8am.
        _seed_workflow(
            registry, "wf_fresh",
            last_deployed=(now - timedelta(hours=2)).isoformat(),
            last_run=None,
            run_count_30d=0,
        )
        result = await tool.execute(
            WorkflowManageInput(action="health_check"), ctx,
        )
        assert result.is_error is False
        rows = result.content["workflows"]
        fresh = next(r for r in rows if r["name"] == "wf_fresh")
        assert fresh["failure_rate_pct"] is None
        # last_deployed is the fallback reference when last_run is None
        # (per 09-RESEARCH.md + D-21).
        assert isinstance(fresh["overdue"], bool)

    async def test_health_check_overdue(self, tool, registry, ctx):
        # last_run is 3 days ago for a daily 8am schedule -> overdue = True
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _seed_workflow(registry, "wf_old", schedule="0 8 * * *", last_run=old)
        result = await tool.execute(
            WorkflowManageInput(action="health_check"), ctx,
        )
        row = next(r for r in result.content["workflows"] if r["name"] == "wf_old")
        assert row["overdue"] is True

    async def test_health_check_skips_paused_for_overdue(
        self, tool, registry, ctx,
    ):
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _seed_workflow(
            registry, "wf_paused", status="paused",
            schedule="0 8 * * *", last_run=old,
        )
        result = await tool.execute(
            WorkflowManageInput(action="health_check"), ctx,
        )
        # Per plan review note #2: paused workflows appear in result rows
        # with overdue=False (not excluded from rows).
        row = next(
            r for r in result.content["workflows"] if r["name"] == "wf_paused"
        )
        assert row["overdue"] is False  # paused workflows can't be overdue (D-16)

    async def test_health_check_failure_rate_computed_when_run_count_positive(
        self, tool, registry, ctx,
    ):
        _seed_workflow(
            registry, "wf_fail",
            run_count_30d=10,
            failure_count_30d=3,
            last_run=datetime.now(timezone.utc).isoformat(),
        )
        result = await tool.execute(
            WorkflowManageInput(action="health_check"), ctx,
        )
        row = next(
            r for r in result.content["workflows"] if r["name"] == "wf_fail"
        )
        assert row["failure_rate_pct"] == pytest.approx(30.0, rel=1e-3)
