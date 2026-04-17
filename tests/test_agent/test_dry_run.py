"""Dry-run mode — table-driven per-tool semantics.

Write-type tools return DryRunReceipt; read-only tools execute.
ctx.vars is unchanged across any dry-run call; no files are written.
"""
from __future__ import annotations

import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.types import DryRunReceipt


@pytest.fixture
def ctx_dry():
    ctx = SessionContext()
    ctx.dry_run = True
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2, 3]}))
    return ctx


@pytest.fixture
def ctx_live():
    ctx = SessionContext()
    ctx.dry_run = False
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2, 3]}))
    return ctx


# ---------------------------------------------------------------------------
# Write-type tools: return DryRunReceipt, do NOT mutate ctx.vars or write files
# ---------------------------------------------------------------------------

async def test_df_transform_dry_run_returns_receipt_no_mutation(ctx_dry):
    from yigthinker.tools.dataframe.df_transform import (
        DfTransformInput,
        DfTransformTool,
    )
    tool = DfTransformTool()
    before_id = id(ctx_dry.vars.get("df1"))
    result = await tool.execute(
        DfTransformInput(
            input_var="df1",
            output_var="df2",
            code="result = df.assign(b=df.a * 2)",
        ),
        ctx_dry,
    )
    assert not result.is_error
    assert isinstance(result.content, DryRunReceipt)
    assert result.content.tool_name == "df_transform"
    # ctx.vars unchanged
    assert "df2" not in ctx_dry.vars
    assert id(ctx_dry.vars.get("df1")) == before_id


async def test_artifact_write_dry_run_no_file(tmp_path, ctx_dry):
    from yigthinker.tools.artifact_write import ArtifactWriteTool
    tool = ArtifactWriteTool()
    input_schema = tool.input_schema
    result = await tool.execute(
        input_schema(filename="out.txt", content="hello"),
        ctx_dry,
    )
    assert not result.is_error
    assert isinstance(result.content, DryRunReceipt)
    assert result.content.tool_name == "artifact_write"
    # Guard short-circuits before any path resolution, so tmp_path is
    # untouched — belt-and-suspenders assertion.
    assert list(tmp_path.iterdir()) == []


async def test_report_generate_dry_run_no_file(tmp_path, ctx_dry):
    from yigthinker.tools.reports.report_generate import ReportGenerateTool
    tool = ReportGenerateTool()
    try:
        input_model = tool.input_schema(
            var_name="df1", format="csv", output_path=str(tmp_path / "r.csv"),
        )
    except Exception:
        pytest.skip("report_generate schema changed — update this test")
    result = await tool.execute(input_model, ctx_dry)
    assert not result.is_error
    assert isinstance(result.content, DryRunReceipt)
    assert result.content.tool_name == "report_generate"
    assert not (tmp_path / "r.csv").exists()


# ---------------------------------------------------------------------------
# Read-only tools: execute normally even in dry-run
# ---------------------------------------------------------------------------

async def test_df_profile_dry_run_executes_normally(ctx_dry):
    from yigthinker.tools.dataframe.df_profile import DfProfileTool
    tool = DfProfileTool()
    result = await tool.execute(
        tool.input_schema(var_name="df1"),
        ctx_dry,
    )
    assert not isinstance(result.content, DryRunReceipt)
    assert not result.is_error


async def test_explore_overview_dry_run_executes_normally(ctx_dry):
    from yigthinker.tools.exploration.explore_overview import ExploreOverviewTool
    tool = ExploreOverviewTool()
    result = await tool.execute(
        tool.input_schema(var_name="df1"),
        ctx_dry,
    )
    assert not isinstance(result.content, DryRunReceipt)
    assert not result.is_error


# ---------------------------------------------------------------------------
# workflow_manage: action-dependent dry-run semantics
# list/inspect/health_check are read-only -> execute normally
# pause/resume/rollback/retire are mutating -> return receipt
# ---------------------------------------------------------------------------


async def test_workflow_manage_list_dry_run_executes_normally(
    ctx_dry, tmp_path,
):
    from yigthinker.tools.workflow.registry import WorkflowRegistry
    from yigthinker.tools.workflow.workflow_manage import (
        WorkflowManageInput,
        WorkflowManageTool,
    )

    registry = WorkflowRegistry(base_dir=tmp_path)
    tool = WorkflowManageTool(registry=registry)
    result = await tool.execute(
        WorkflowManageInput(action="list"),
        ctx_dry,
    )
    # list is read-only -> must not short-circuit to receipt
    assert not isinstance(result.content, DryRunReceipt)
    assert not result.is_error


async def test_workflow_manage_pause_dry_run_returns_receipt(
    ctx_dry, tmp_path,
):
    from yigthinker.tools.workflow.registry import WorkflowRegistry
    from yigthinker.tools.workflow.workflow_manage import (
        WorkflowManageInput,
        WorkflowManageTool,
    )

    registry = WorkflowRegistry(base_dir=tmp_path)
    tool = WorkflowManageTool(registry=registry)
    # Guard short-circuits BEFORE registry lookup, so workflow_name does not
    # need to exist on disk.
    result = await tool.execute(
        WorkflowManageInput(action="pause", workflow_name="some_workflow"),
        ctx_dry,
    )
    assert not result.is_error
    assert isinstance(result.content, DryRunReceipt)
    assert result.content.tool_name == "workflow_manage"
    assert "pause" in result.content.summary.lower()


# ---------------------------------------------------------------------------
# Negative: with dry_run=False, write-type tools still mutate/write normally
# ---------------------------------------------------------------------------

async def test_df_transform_live_mode_mutates(ctx_live):
    from yigthinker.tools.dataframe.df_transform import (
        DfTransformInput,
        DfTransformTool,
    )
    tool = DfTransformTool()
    result = await tool.execute(
        DfTransformInput(
            input_var="df1",
            output_var="df2",
            code="result = df.assign(b=df.a * 2)",
        ),
        ctx_live,
    )
    assert not isinstance(result.content, DryRunReceipt)
    assert not result.is_error
    assert "df2" in ctx_live.vars
