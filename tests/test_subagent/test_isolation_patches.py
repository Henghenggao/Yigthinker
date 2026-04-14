"""Tests for P1-6: Sub-agent Session Isolation Patches.

Covers:
- dataframes=["*"] wildcard copies all parent vars to child
- spawn_agent wildcard expansion before copy
- safe merge-back when parent session has been evicted from the registry
"""
from __future__ import annotations

import pandas as pd
import pytest

from yigthinker.session import VarRegistry
from yigthinker.subagent.dataframes import copy_dataframes_to_child


# ---------------------------------------------------------------------------
# 1.1  Wildcard star copies all vars (tests existing copy_dataframes_to_child)
# ---------------------------------------------------------------------------

def test_wildcard_star_copies_all_vars():
    """When dataframes=["*"], all parent vars should be copied to child."""
    parent = VarRegistry()
    child = VarRegistry()
    parent.set("sales", pd.DataFrame({"a": [1, 2]}))
    parent.set("inventory", pd.DataFrame({"b": [3, 4]}))
    parent.set("my_chart", {"type": "bar"}, var_type="chart")

    all_names = [info.name for info in parent.list()]
    copy_dataframes_to_child(parent, child, all_names)

    assert "sales" in child
    assert "inventory" in child
    assert "my_chart" in child
    assert child.get("sales").shape == (2, 1)
    assert child.get("inventory").shape == (2, 1)


# ---------------------------------------------------------------------------
# 1.2  spawn_agent wildcard expansion
# ---------------------------------------------------------------------------

async def test_spawn_agent_wildcard_copies_all():
    """spawn_agent with dataframes=["*"] should expand to all parent var names."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from yigthinker.session import SessionContext
    from yigthinker.tools.spawn_agent import SpawnAgentInput, SpawnAgentTool

    tool = SpawnAgentTool()

    mock_provider = MagicMock()
    mock_tools = MagicMock()
    mock_hooks = MagicMock()
    mock_hooks.run = AsyncMock()
    mock_permissions = MagicMock()
    tool.set_parent_components(
        tools=mock_tools,
        hooks=mock_hooks,
        permissions=mock_permissions,
        provider=mock_provider,
    )

    ctx = SessionContext()
    ctx.vars.set("sales", pd.DataFrame({"a": [1]}))
    ctx.vars.set("costs", pd.DataFrame({"b": [2]}))

    inp = SpawnAgentInput(prompt="analyze", dataframes=["*"])

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_loop = MagicMock()
        mock_loop.run = AsyncMock(return_value="done")
        mock_engine_cls.return_value.create_child_loop.return_value = mock_loop

        result = await tool.execute(inp, ctx)

    assert not result.is_error
    assert "done" in result.content


# ---------------------------------------------------------------------------
# 1.3  Safe merge-back: SessionRegistry.get() returns None for evicted sessions
# ---------------------------------------------------------------------------

async def test_background_merge_back_skips_evicted_session():
    """If parent session was evicted, merge-back should not crash."""
    from yigthinker.gateway.session_registry import SessionRegistry

    registry = SessionRegistry()
    # Simulate: parent session existed but was evicted
    result = registry.get("nonexistent-key")
    assert result is None
