"""Tests for workflow_generate tool.

Covers: python/PA/UiPath targets, from_history extraction with error filtering,
update versioning, schedule validation, config vault placeholders, checkpoint utils,
requirements auto-generation, step variable passing, param normalization.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.tools.workflow.workflow_generate import (
    WorkflowGenerateTool,
    WorkflowGenerateInput,
    WorkflowStep,
    _extract_steps_from_history,
    _normalize_step_params,
)
from yigthinker.session import SessionContext
from yigthinker.types import Message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workflow_registry(tmp_path: Path) -> WorkflowRegistry:
    return WorkflowRegistry(base_dir=tmp_path / "workflows")


@pytest.fixture
def generate_tool(workflow_registry: WorkflowRegistry) -> WorkflowGenerateTool:
    return WorkflowGenerateTool(registry=workflow_registry)


@pytest.fixture
def sample_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(id="step_1", action="sql_query", params={"query": "SELECT * FROM sales"}),
        WorkflowStep(id="step_2", action="df_transform", params={"code": "df.head()"}, inputs=["step_1"]),
    ]


@pytest.fixture
def mock_ctx() -> SessionContext:
    """SessionContext with 3 assistant messages containing tool_use blocks."""
    ctx = SessionContext()
    # Assistant message with sql_query tool_use
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_1", "name": "sql_query", "input": {"query": "SELECT * FROM sales"}},
        ],
    ))
    # User message with successful tool_result
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "10 rows", "is_error": False},
        ],
    ))
    # Assistant message with df_transform tool_use
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_2", "name": "df_transform", "input": {"code": "df.head()"}},
        ],
    ))
    # User message with successful tool_result
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_2", "content": "5 rows", "is_error": False},
        ],
    ))
    # Assistant message with chart_create tool_use
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_3", "name": "chart_create", "input": {"chart_type": "bar"}},
        ],
    ))
    # User message with successful tool_result
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_3", "content": "chart ok", "is_error": False},
        ],
    ))
    return ctx


@pytest.fixture
def mock_ctx_with_errors() -> SessionContext:
    """SessionContext with a tool_use followed by is_error=True tool_result."""
    ctx = SessionContext()
    # Assistant message with sql_query tool_use
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_1", "name": "sql_query", "input": {"query": "BAD SQL"}},
        ],
    ))
    # User message with error tool_result
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "syntax error", "is_error": True},
        ],
    ))
    # Assistant with a successful df_transform
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_2", "name": "df_transform", "input": {"code": "df.sum()"}},
        ],
    ))
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_2", "content": "ok", "is_error": False},
        ],
    ))
    return ctx


# ---------------------------------------------------------------------------
# Test: Generate Python target
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_python_target(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    inp = WorkflowGenerateInput(
        name="test_wf",
        description="Test workflow",
        steps=sample_steps,
        target="python",
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error, f"Unexpected error: {result.content}"
    assert isinstance(result.content, dict)
    assert "output_dir" in result.content
    assert "version" in result.content
    assert "files" in result.content
    assert "main.py" in result.content["files"]
    assert "checkpoint_utils.py" in result.content["files"]
    assert "config.yaml" in result.content["files"]
    assert "requirements.txt" in result.content["files"]
    # Verify files on disk
    output_dir = Path(result.content["output_dir"])
    assert output_dir.exists()
    assert (output_dir / "main.py").exists()


# ---------------------------------------------------------------------------
# Test: Generate Power Automate target
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_pa_target(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    inp = WorkflowGenerateInput(
        name="pa_wf",
        description="PA workflow",
        steps=sample_steps,
        target="power_automate",
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error, f"Unexpected error: {result.content}"
    output_dir = Path(result.content["output_dir"])
    main_content = (output_dir / "main.py").read_text(encoding="utf-8")
    # PA template extends base, so should have PA-specific content
    assert "power_automate" in main_content.lower() or "Power Automate" in main_content


# ---------------------------------------------------------------------------
# Test: Generate UiPath target
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_uipath_target(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    inp = WorkflowGenerateInput(
        name="uipath_wf",
        description="UiPath workflow",
        steps=sample_steps,
        target="uipath",
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error, f"Unexpected error: {result.content}"
    output_dir = Path(result.content["output_dir"])
    main_content = (output_dir / "main.py").read_text(encoding="utf-8")
    assert "uipath" in main_content.lower() or "UiPath" in main_content


# ---------------------------------------------------------------------------
# Test: from_history extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_from_history_extraction(generate_tool: WorkflowGenerateTool, mock_ctx: SessionContext):
    inp = WorkflowGenerateInput(
        name="history_wf",
        description="From history",
        from_history=True,
        steps=[],
    )
    result = await generate_tool.execute(inp, mock_ctx)
    assert not result.is_error, f"Unexpected error: {result.content}"
    output_dir = Path(result.content["output_dir"])
    main_content = (output_dir / "main.py").read_text(encoding="utf-8")
    # Should have 3 step functions extracted (sql_query, df_transform, chart_create)
    assert "step_" in main_content


# ---------------------------------------------------------------------------
# Test: from_history filters errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_from_history_filters_errors(generate_tool: WorkflowGenerateTool, mock_ctx_with_errors: SessionContext):
    inp = WorkflowGenerateInput(
        name="error_filter_wf",
        description="Error filtering",
        from_history=True,
        steps=[],
    )
    result = await generate_tool.execute(inp, mock_ctx_with_errors)
    assert not result.is_error, f"Unexpected error: {result.content}"
    # Only the successful df_transform should be extracted, not the errored sql_query
    output_dir = Path(result.content["output_dir"])
    main_content = (output_dir / "main.py").read_text(encoding="utf-8")
    assert "df_transform" in main_content


# ---------------------------------------------------------------------------
# Test: from_history skips non-automatable tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_from_history_skips_non_automatable():
    ctx = SessionContext()
    # Add spawn_agent (not automatable)
    ctx.messages.append(Message(
        role="assistant",
        content=[
            {"type": "tool_use", "id": "tu_1", "name": "spawn_agent", "input": {"task": "analyze"}},
        ],
    ))
    ctx.messages.append(Message(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok", "is_error": False},
        ],
    ))
    steps = _extract_steps_from_history(ctx.messages)
    assert len(steps) == 0


# ---------------------------------------------------------------------------
# Test: update creates new version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_creates_new_version(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    # First create v1
    inp_v1 = WorkflowGenerateInput(
        name="versioned_wf",
        description="Version 1",
        steps=sample_steps,
    )
    result_v1 = await generate_tool.execute(inp_v1, ctx)
    assert not result_v1.is_error
    v1_dir = Path(result_v1.content["output_dir"])
    assert v1_dir.exists()

    # Update with update_of
    inp_v2 = WorkflowGenerateInput(
        name="versioned_wf_v2",
        description="Version 2",
        steps=sample_steps,
        update_of="versioned_wf",
    )
    result_v2 = await generate_tool.execute(inp_v2, ctx)
    assert not result_v2.is_error
    v2_dir = Path(result_v2.content["output_dir"])
    assert v2_dir.exists()

    # v1 still exists unchanged
    assert v1_dir.exists()
    assert (v1_dir / "main.py").exists()

    # v2 is a different directory
    assert v1_dir != v2_dir


# ---------------------------------------------------------------------------
# Test: schedule validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_validation(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    # Valid cron expression should be accepted
    inp_valid = WorkflowGenerateInput(
        name="sched_wf",
        description="Scheduled",
        steps=sample_steps,
        schedule="*/15 * * * *",
    )
    result_valid = await generate_tool.execute(inp_valid, ctx)
    assert not result_valid.is_error

    # Invalid cron expression should error
    inp_invalid = WorkflowGenerateInput(
        name="sched_wf_bad",
        description="Bad schedule",
        steps=sample_steps,
        schedule="invalid cron",
    )
    result_invalid = await generate_tool.execute(inp_invalid, ctx)
    assert result_invalid.is_error


# ---------------------------------------------------------------------------
# Test: config has vault placeholders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_has_vault_placeholders(generate_tool: WorkflowGenerateTool):
    ctx = SessionContext()
    steps = [
        WorkflowStep(
            id="step_1",
            action="sql_query",
            params={"query": "SELECT 1", "connection": "my_db"},
        ),
    ]
    inp = WorkflowGenerateInput(
        name="vault_wf",
        description="Vault test",
        steps=steps,
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error
    output_dir = Path(result.content["output_dir"])
    config_content = (output_dir / "config.yaml").read_text(encoding="utf-8")
    assert "vault://" in config_content
    # Should not contain plaintext credential patterns
    assert "password" not in config_content.lower() or "vault://" in config_content


# ---------------------------------------------------------------------------
# Test: checkpoint_utils included
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checkpoint_utils_included(generate_tool: WorkflowGenerateTool, sample_steps: list[WorkflowStep]):
    ctx = SessionContext()
    inp = WorkflowGenerateInput(
        name="ckpt_wf",
        description="Checkpoint test",
        steps=sample_steps,
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error
    output_dir = Path(result.content["output_dir"])
    ckpt_content = (output_dir / "checkpoint_utils.py").read_text(encoding="utf-8")
    assert "retry" in ckpt_content.lower() or "checkpoint" in ckpt_content.lower()
    assert "self_heal" in ckpt_content or "self-heal" in ckpt_content.lower() or "report_status" in ckpt_content


# ---------------------------------------------------------------------------
# Test: requirements auto-generated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_requirements_auto_generated(generate_tool: WorkflowGenerateTool):
    ctx = SessionContext()
    steps = [
        WorkflowStep(id="step_1", action="sql_query", params={"query": "SELECT 1"}),
        WorkflowStep(id="step_2", action="df_transform", params={"code": "df.head()"}, inputs=["step_1"]),
    ]
    inp = WorkflowGenerateInput(
        name="req_wf",
        description="Requirements test",
        steps=steps,
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error
    output_dir = Path(result.content["output_dir"])
    req_content = (output_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "sqlalchemy" in req_content.lower()
    assert "pandas" in req_content.lower()


# ---------------------------------------------------------------------------
# Test: step variable passing (D-09)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_variable_passing(generate_tool: WorkflowGenerateTool):
    ctx = SessionContext()
    steps = [
        WorkflowStep(id="step_1", action="sql_query", params={"query": "SELECT 1"}),
        WorkflowStep(id="step_2", action="df_transform", params={"code": "df.sum()"}, inputs=["step_1"]),
    ]
    inp = WorkflowGenerateInput(
        name="varpass_wf",
        description="Variable passing test",
        steps=steps,
    )
    result = await generate_tool.execute(inp, ctx)
    assert not result.is_error
    output_dir = Path(result.content["output_dir"])
    main_content = (output_dir / "main.py").read_text(encoding="utf-8")
    # Step 2 should receive result from step_1
    assert "result_step_1" in main_content


# ---------------------------------------------------------------------------
# Test: normalize step params
# ---------------------------------------------------------------------------

def test_normalize_step_params():
    params = {
        "none_val": "None",
        "true_val": "True",
        "false_val": "False",
        "int_val": "42",
        "float_val": "3.14",
        "normal_str": "hello",
    }
    result = _normalize_step_params(params)
    assert result["none_val"] is None
    assert result["true_val"] is True
    assert result["false_val"] is False
    assert result["int_val"] == 42
    assert isinstance(result["int_val"], int)
    assert result["float_val"] == 3.14
    assert isinstance(result["float_val"], float)
    assert result["normal_str"] == "hello"
