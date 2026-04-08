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
    assert inp.allowed_tools is None
    assert inp.agent_type is None


async def test_spawn_agent_returns_stub_error(ctx):
    tool = SpawnAgentTool()
    inp = SpawnAgentInput(prompt="Summarize the sales data")
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "structure validated" in result.content


async def test_spawn_agent_with_dataframes_still_returns_error(ctx):
    tool = SpawnAgentTool()
    inp = SpawnAgentInput(prompt="analyze", dataframes=["sales"])
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "structure validated" in result.content
