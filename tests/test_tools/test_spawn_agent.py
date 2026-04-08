from __future__ import annotations

import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.spawn_agent import SpawnAgentInput, SpawnAgentTool
from yigthinker.types import ToolResult


@pytest.fixture
def ctx():
    return SessionContext()


def test_spawn_agent_input_schema():
    inp = SpawnAgentInput(prompt="Analyze East region")
    assert inp.prompt == "Analyze East region"
    assert inp.dataframes is None
    assert inp.background is False


async def test_spawn_agent_returns_error_when_not_initialized(ctx):
    """spawn_agent returns error when parent components are not set."""
    tool = SpawnAgentTool()
    inp = SpawnAgentInput(prompt="Summarize the sales data")
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "not fully initialized" in result.content


async def test_spawn_agent_has_set_parent_components():
    """SpawnAgentTool exposes set_parent_components method."""
    tool = SpawnAgentTool()
    assert hasattr(tool, "set_parent_components")
