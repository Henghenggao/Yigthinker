# tests/test_tools/test_agent_status.py
# Tests for AgentStatusTool (SPAWN-13)
import time

import pytest

from yigthinker.session import SessionContext
from yigthinker.subagent.manager import SubagentManager
from yigthinker.tools.agent_status import AgentStatusInput, AgentStatusTool


async def test_no_subagents():
    """Returns message when subagent_manager is None."""
    tool = AgentStatusTool()
    ctx = SessionContext()
    assert ctx.subagent_manager is None

    result = await tool.execute(AgentStatusInput(), ctx)
    assert not result.is_error
    assert "No subagents have been spawned" in result.content


async def test_no_subagents_empty_manager():
    """Returns message when manager exists but has no subagents."""
    tool = AgentStatusTool()
    ctx = SessionContext()
    ctx.subagent_manager = SubagentManager()

    result = await tool.execute(AgentStatusInput(), ctx)
    assert not result.is_error
    assert "No subagents have been spawned" in result.content


async def test_lists_running():
    """Lists a running subagent with name, id prefix, status, and elapsed time."""
    tool = AgentStatusTool()
    ctx = SessionContext()
    mgr = SubagentManager()
    ctx.subagent_manager = mgr

    info = mgr.register("east-analyst")

    result = await tool.execute(AgentStatusInput(), ctx)
    assert not result.is_error
    assert "east-analyst" in result.content
    assert info.subagent_id[:8] in result.content
    assert "running" in result.content


async def test_lists_multiple():
    """Lists multiple subagents with different statuses."""
    tool = AgentStatusTool()
    ctx = SessionContext()
    mgr = SubagentManager()
    ctx.subagent_manager = mgr

    info1 = mgr.register("east-analyst")
    info2 = mgr.register("west-analyst")
    mgr.complete(info2.subagent_id, "done")

    result = await tool.execute(AgentStatusInput(), ctx)
    assert not result.is_error
    assert "east-analyst" in result.content
    assert "west-analyst" in result.content
    assert "running" in result.content
    assert "completed" in result.content
