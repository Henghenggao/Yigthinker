from __future__ import annotations
import pandas as pd
import pytest
from unittest.mock import AsyncMock, patch
from yigthinker.tools.spawn_agent import SpawnAgentTool, SpawnAgentInput
from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


@pytest.fixture
def ctx():
    c = SessionContext()
    c.vars.set("sales", pd.DataFrame({"region": ["North", "South"], "revenue": [100, 200]}))
    return c


def test_spawn_agent_input_schema():
    inp = SpawnAgentInput(prompt="Analyze East region")
    assert inp.prompt == "Analyze East region"
    assert inp.dataframes is None
    assert inp.background is False


async def test_spawn_agent_returns_tool_result(ctx):
    tool = SpawnAgentTool()
    inp = SpawnAgentInput(
        prompt="Summarize the sales data",
        dataframes=["sales"],
    )
    with patch.object(tool, "_run_subagent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Subagent completed: North=100, South=200"
        result = await tool.execute(inp, ctx)
    assert not result.is_error
    assert "Subagent" in result.content


async def test_spawn_agent_dataframe_isolation(ctx):
    """Subagent receives a snapshot copy, not the original DataFrame."""
    tool = SpawnAgentTool()
    snapshots_received = []

    async def capture_snapshot(prompt, snapshot, **kwargs):
        snapshots_received.append(snapshot)
        return "done"

    with patch.object(tool, "_run_subagent", side_effect=capture_snapshot):
        inp = SpawnAgentInput(prompt="analyze", dataframes=["sales"])
        await tool.execute(inp, ctx)

    assert len(snapshots_received) == 1
    # Snapshot contains copy of 'sales'
    assert "sales" in snapshots_received[0]
    # Original is unmodified
    assert ctx.vars.get("sales") is not None


async def test_spawn_agent_missing_dataframe_returns_error(ctx):
    tool = SpawnAgentTool()
    inp = SpawnAgentInput(prompt="analyze", dataframes=["nonexistent"])
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "nonexistent" in result.content
