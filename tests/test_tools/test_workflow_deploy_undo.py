"""P1-3 per-tool integration: workflow_deploy must snapshot local artifacts
before writing.

Scope covered:
- `_deploy_local` writes 3 files under `local_guided/` — each needs a snapshot
- `_deploy_guided` writes `setup_guide.md` under the guided output dir —
  needs a snapshot

Out of scope (per P1-3 spec "External side effects are NEVER rolled back"):
- the deployment itself (the registry entry, the cron install, the MCP call)
"""
from __future__ import annotations

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
    return SessionContext()


async def _generate_sample_workflow(
    workflow_registry: WorkflowRegistry,
    ctx: SessionContext,
    name: str = "monthly_ar_aging",
) -> None:
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


async def test_deploy_local_snapshots_three_artifacts(workflow_registry, ctx, tmp_path):
    """Local-mode deploy writes 3 files; each must be recorded in undo_stack."""
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
    # Expected 3 entries — one per file (xml, crontab, setup_guide)
    assert len(ctx.undo_stack) == 3
    originals = {e.original_path.name for e in ctx.undo_stack}
    assert originals == {"task_scheduler.xml", "crontab.txt", "setup_guide.md"}
    assert all(e.tool_name == "workflow_deploy" for e in ctx.undo_stack)
    # First deploy creates these fresh — all entries should be new-file
    assert all(e.is_new_file for e in ctx.undo_stack)
    assert all(e.backup_path is None for e in ctx.undo_stack)


async def test_deploy_local_second_run_backs_up_existing(workflow_registry, ctx, tmp_path):
    """Re-running local deploy at same version overwrites existing artifacts;
    the second run must produce UndoEntry records with backups."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)

    inp = WorkflowDeployInput(
        workflow_name="monthly_ar_aging",
        target="local",
        deploy_mode="local",
        schedule="0 8 5 * *",
    )

    # First run — artifacts are created
    r1 = await tool.execute(inp, ctx)
    assert not r1.is_error
    assert len(ctx.undo_stack) == 3

    # Second run — same version_dir/local_guided, files already exist
    r2 = await tool.execute(inp, ctx)
    assert not r2.is_error
    # 3 new entries appended — all with backups because files now exist
    assert len(ctx.undo_stack) == 6
    second_run_entries = ctx.undo_stack[3:]
    assert all(not e.is_new_file for e in second_run_entries)
    assert all(e.backup_path is not None and e.backup_path.exists()
               for e in second_run_entries)


async def test_deploy_dry_run_does_not_snapshot(workflow_registry, ctx, tmp_path):
    """Dry-run must not create any undo entries."""
    from yigthinker.tools.workflow.workflow_deploy import (
        WorkflowDeployInput,
        WorkflowDeployTool,
    )
    await _generate_sample_workflow(workflow_registry, ctx)
    tool = WorkflowDeployTool(registry=workflow_registry)
    ctx.dry_run = True

    result = await tool.execute(
        WorkflowDeployInput(
            workflow_name="monthly_ar_aging",
            target="local",
            deploy_mode="local",
            schedule="0 8 5 * *",
        ),
        ctx,
    )
    assert not result.is_error
    assert len(ctx.undo_stack) == 0


async def test_deploy_guided_snapshots_setup_guide(workflow_registry, ctx, tmp_path):
    """Guided-mode deploy writes a setup_guide.md — must be snapshot-recorded."""
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
    # Guided mode builds a bundle + writes one setup_guide.md — exactly 1 entry
    assert len(ctx.undo_stack) == 1
    entry = ctx.undo_stack[-1]
    assert entry.original_path.name == "setup_guide.md"
    assert entry.tool_name == "workflow_deploy"
