"""Tests for WorkflowDeployTool -- Plan 09-01 (local mode) + 09-02 stubs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.tools.workflow.workflow_generate import (
    WorkflowGenerateInput,
    WorkflowGenerateTool,
    WorkflowStep,
)


@pytest.fixture
def workflow_registry(tmp_path: Path) -> WorkflowRegistry:
    return WorkflowRegistry(base_dir=tmp_path)


@pytest.fixture
def ctx() -> SessionContext:
    # Phase 8 pattern: zero-arg SessionContext() — uses default_factory for all fields
    # including vars=VarRegistry(). workflow_deploy never reads ctx.vars, but the
    # real SessionContext has a VarRegistry (not None), so match the real shape.
    return SessionContext()


async def _generate_sample_workflow(
    workflow_registry: WorkflowRegistry,
    ctx: SessionContext,
    name: str = "monthly_ar_aging",
) -> None:
    """Use WorkflowGenerateTool to create a v1 workflow we can deploy against."""
    gen = WorkflowGenerateTool(registry=workflow_registry)
    result = await gen.execute(
        WorkflowGenerateInput(
            name=name,
            description="Monthly AR aging",
            steps=[
                WorkflowStep(
                    id="step_1",
                    action="sql_query",
                    params={"query": "SELECT 1"},
                ),
            ],
            target="python",
            schedule="0 8 5 * *",
        ),
        ctx,
    )
    assert not result.is_error, f"fixture setup failed: {result.content}"


async def test_local_mode(workflow_registry, ctx, tmp_path):
    """DEP-01: local mode writes task_scheduler.xml + crontab.txt + setup_guide.md into local_guided/."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)

    result = await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 5 * *",
        ),
        ctx,
    )

    assert not result.is_error, result.content
    version_dir = tmp_path / "monthly_ar_aging" / "v1"
    local_dir = version_dir / "local_guided"
    assert (local_dir / "task_scheduler.xml").is_file()
    assert (local_dir / "crontab.txt").is_file()
    assert (local_dir / "setup_guide.md").is_file()


async def test_task_scheduler_xml_shape(workflow_registry, ctx, tmp_path):
    """DEP-01: generated XML parses and contains absolute python path + working directory."""
    import xml.etree.ElementTree as ET
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 * * *",
        ),
        ctx,
    )

    xml_path = tmp_path / "monthly_ar_aging" / "v1" / "local_guided" / "task_scheduler.xml"
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
    assert root.tag == f"{ns}Task"
    assert root.attrib["version"] == "1.3"
    cmd = root.find(f".//{ns}Command")
    assert cmd is not None
    # Must be an absolute path (resolved via sys.executable at generation time)
    assert Path(cmd.text).is_absolute()
    wd = root.find(f".//{ns}WorkingDirectory")
    assert wd is not None
    assert "monthly_ar_aging" in wd.text


async def test_crontab_txt_shape(workflow_registry, ctx, tmp_path):
    """DEP-01: crontab has PATH= line, cd + python + log redirect, trailing newline."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 * * *",
        ),
        ctx,
    )
    cron_path = tmp_path / "monthly_ar_aging" / "v1" / "local_guided" / "crontab.txt"
    text = cron_path.read_text(encoding="utf-8")
    assert "PATH=" in text
    assert "0 8 * * *" in text
    assert "main.py" in text
    assert ">> run.log 2>&1" in text
    assert text.endswith("\n")
    # POSIX only -- no backslashes in crontab paths
    assert "\\" not in text


async def test_cron_to_taskscheduler(workflow_registry, ctx, tmp_path):
    """DEP-01: dispatcher handles daily / monthly / weekly / every-N-hours."""
    from datetime import datetime, timezone

    from yigthinker.tools.workflow.workflow_deploy import cron_to_ts_trigger

    ref = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)

    assert cron_to_ts_trigger("0 8 * * *", ref)["kind"] == "calendar_daily"
    monthly = cron_to_ts_trigger("0 8 5 * *", ref)
    assert monthly["kind"] == "calendar_monthly"
    assert monthly["day_of_month"] == 5
    weekly = cron_to_ts_trigger("0 8 * * 1", ref)
    assert weekly["kind"] == "calendar_weekly"
    assert weekly["day_of_week"] == "Monday"
    hourly = cron_to_ts_trigger("0 */4 * * *", ref)
    assert hourly["kind"] == "calendar_hourly"
    assert hourly["interval_hours"] == 4
    # Fallback
    odd = cron_to_ts_trigger("15 3 * * 1-5", ref)
    assert odd["kind"] == "calendar_daily"
    assert odd["needs_manual_review"] is True


async def test_invalid_target_mode_combo(workflow_registry, ctx):
    """DEP-04: target=local requires deploy_mode=local; reject other combos."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    result = await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="auto",
            schedule="0 8 * * *",
        ),
        ctx,
    )
    assert result.is_error
    assert "local" in str(result.content).lower()


async def test_invalid_schedule_fails_fast(workflow_registry, ctx):
    """Invalid cron expression -> is_error without writing artifacts."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    result = await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="not a cron",
        ),
        ctx,
    )
    assert result.is_error
    assert "cron" in str(result.content).lower()


async def test_deploy_writes_registry_metadata(workflow_registry, ctx, tmp_path):
    """DEP-05: after local deploy, registry.json entry has target/deploy_mode/schedule/last_deployed/deploy_id."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 5 * *",
        ),
        ctx,
    )
    index = workflow_registry.load_index()
    entry = index["workflows"]["monthly_ar_aging"]
    assert entry["target"] == "local"
    assert entry["deploy_mode"] == "local"
    assert entry["schedule"] == "0 8 5 * *"
    assert entry["last_deployed"] is not None
    assert entry["deploy_id"]
    assert "monthly_ar_aging-v1-local" in entry["deploy_id"]
    assert entry["current_version"] == 1


async def test_deploy_writes_manifest_metadata(workflow_registry, ctx, tmp_path):
    """DEP-05: version entry inside manifest.json has deployed_to/deploy_mode/deploy_id/status=active."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 5 * *",
        ),
        ctx,
    )
    manifest = workflow_registry.get_manifest("monthly_ar_aging")
    v1 = manifest["versions"][0]
    assert v1["deployed_to"] == "local"
    assert v1["deploy_mode"] == "local"
    assert v1["status"] == "active"
    assert v1["deploy_id"]


# ---------------------------------------------------------------------------
# Phase 9 Plan 02: Guided mode (DEP-02)
# ---------------------------------------------------------------------------


class TestWorkflowDeployGuided:
    """DEP-02: guided mode for PA + UiPath."""

    async def test_guided_mode_power_automate(
        self, workflow_registry, ctx, tmp_path,
    ):
        """test_guided_mode - canonical row 09-02-03."""
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)

        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="power_automate",
                deploy_mode="guided",
                schedule="0 8 5 * *",
            ),
            ctx,
        )
        assert not result.is_error, result.content
        content = result.content
        assert content["mode"] == "guided"
        assert content["target"] == "power_automate"
        bundle = Path(content["artifacts_ready"]["bundle"])
        assert bundle.exists()
        assert bundle.name == "flow_import.zip"

    async def test_guided_mode_uipath(
        self, workflow_registry, ctx, tmp_path,
    ):
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="uipath",
                deploy_mode="guided",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert not result.is_error, result.content
        content = result.content
        assert content["mode"] == "guided"
        assert content["target"] == "uipath"
        bundle = Path(content["artifacts_ready"]["bundle"])
        assert bundle.exists()
        assert bundle.name == "process_package.zip"

    async def test_guided_updates_registry_metadata(
        self, workflow_registry, ctx, tmp_path,
    ):
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="power_automate",
                deploy_mode="guided",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        idx = workflow_registry.load_index()
        entry = idx["workflows"]["monthly_ar_aging"]
        assert entry["target"] == "power_automate"
        assert entry["deploy_mode"] == "guided"
        assert entry["schedule"] == "0 8 * * *"
        assert entry["last_deployed"] is not None
        assert entry["deploy_id"].startswith("monthly_ar_aging-v1-guided-")
        manifest = workflow_registry.get_manifest("monthly_ar_aging")
        v1 = manifest["versions"][0]
        assert v1["deployed_to"] == "power_automate"
        assert v1["deploy_mode"] == "guided"
        assert v1["status"] == "active"
        assert v1["deploy_id"].startswith("monthly_ar_aging-v1-guided-")

    async def test_guided_mode_local_target_rejected(
        self, workflow_registry, ctx,
    ):
        """target=local with deploy_mode=guided is rejected (D-23)."""
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="local",
                deploy_mode="guided",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert result.is_error
        assert "local" in str(result.content).lower()


# ---------------------------------------------------------------------------
# Phase 9 Plan 02: Auto mode (DEP-03)
# ---------------------------------------------------------------------------


class TestWorkflowDeployAuto:
    """DEP-03: auto-mode MCP detection handshake."""

    async def test_auto_mode(
        self, workflow_registry, ctx, monkeypatch,
    ):
        """test_auto_mode - canonical row 09-02-04. MCP present path."""
        from yigthinker.tools.workflow import mcp_detection
        monkeypatch.setattr(
            mcp_detection, "check_mcp_installed", lambda pkg: True,
        )
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="power_automate",
                deploy_mode="auto",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert not result.is_error, result.content
        content = result.content
        assert content["mode"] == "auto"
        assert content["mcp_installed"] is True
        assert "next_steps" in content
        assert (
            content["next_steps"]["suggested_tool"]
            == "power_automate_create_flow"
        )
        assert (
            content["next_steps"]["mcp_package"] == "yigthinker_pa_mcp"
        )

    async def test_auto_mode_returns_next_steps(
        self, workflow_registry, ctx, monkeypatch,
    ):
        from yigthinker.tools.workflow import mcp_detection
        monkeypatch.setattr(
            mcp_detection, "check_mcp_installed", lambda pkg: True,
        )
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="uipath",
                deploy_mode="auto",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert not result.is_error, result.content
        assert (
            result.content["next_steps"]["suggested_tool"]
            == "ui_deploy_process"
        )
        assert (
            result.content["next_steps"]["mcp_package"]
            == "yigthinker_mcp_uipath"
        )

    async def test_auto_mode_mcp_missing_error(
        self, workflow_registry, ctx, monkeypatch,
    ):
        """When MCP package is missing, is_error=True with install hint."""
        from yigthinker.tools.workflow import mcp_detection
        monkeypatch.setattr(
            mcp_detection, "check_mcp_installed", lambda pkg: False,
        )
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="power_automate",
                deploy_mode="auto",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert result.is_error
        msg = str(result.content).lower()
        assert "yigthinker_pa_mcp" in msg or "pa-mcp" in msg
        assert "guided" in msg  # suggests fallback

    async def test_auto_mode_local_target_rejected(
        self, workflow_registry, ctx,
    ):
        """target=local with deploy_mode=auto rejected (D-23)."""
        from yigthinker.tools.workflow.workflow_deploy import (
            WorkflowDeployInput,
            WorkflowDeployTool,
        )
        await _generate_sample_workflow(workflow_registry, ctx)
        tool = WorkflowDeployTool(registry=workflow_registry)
        result = await tool.execute(
            WorkflowDeployInput(
                workflow_name="monthly_ar_aging",
                target="local",
                deploy_mode="auto",
                schedule="0 8 * * *",
            ),
            ctx,
        )
        assert result.is_error
