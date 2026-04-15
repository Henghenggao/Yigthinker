# tests/test_tools/test_agent_cancel.py
# Tests for AgentCancelTool (SPAWN-14)
import asyncio
from unittest.mock import MagicMock


from yigthinker.session import SessionContext
from yigthinker.subagent.manager import SubagentManager
from yigthinker.tools.agent_cancel import AgentCancelInput, AgentCancelTool


async def test_cancel_running():
    """Cancel a running subagent with a mock task."""
    tool = AgentCancelTool()
    ctx = SessionContext()
    mgr = SubagentManager()
    ctx.subagent_manager = mgr

    mock_task = MagicMock(spec=asyncio.Task)
    info = mgr.register("cancellable-agent", task=mock_task)

    result = await tool.execute(
        AgentCancelInput(subagent_id=info.subagent_id),
        ctx,
    )
    assert not result.is_error
    assert "cancelled" in result.content
    mock_task.cancel.assert_called_once()


async def test_cancel_not_found():
    """Cancel with unknown id returns error."""
    tool = AgentCancelTool()
    ctx = SessionContext()
    mgr = SubagentManager()
    ctx.subagent_manager = mgr

    result = await tool.execute(
        AgentCancelInput(subagent_id="nonexistent-id"),
        ctx,
    )
    assert result.is_error
    assert "not found or not running" in result.content


async def test_cancel_no_manager():
    """Cancel when subagent_manager is None returns error."""
    tool = AgentCancelTool()
    ctx = SessionContext()
    assert ctx.subagent_manager is None

    result = await tool.execute(
        AgentCancelInput(subagent_id="some-id"),
        ctx,
    )
    assert result.is_error
    assert "No subagents have been spawned" in result.content
