# tests/test_subagent/test_tool_access.py
# Tests for tool access control in child ToolRegistry (SPAWN-07, -08, -09, D-05)
import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.subagent.engine import SubagentEngine
from yigthinker.tools.registry import ToolRegistry
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.tools.sql.sql_query import SqlQueryTool
from yigthinker.types import ToolResult


class StubInput(BaseModel):
    value: str


class StubTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"Stub {name}"
        self.input_schema = StubInput

    async def execute(self, input_obj: StubInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"{self.name}:{input_obj.value}")


def _make_engine(
    tool_names: list[str] | None = None,
    registry: ToolRegistry | None = None,
) -> SubagentEngine:
    """Build a SubagentEngine with stub or provided tools."""
    tools = registry or ToolRegistry()
    if registry is None:
        for name in (tool_names or ["sql_query", "df_transform", "chart_create"]):
            tools.register(StubTool(name))

    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({})
    provider = AsyncMock()
    settings = {"model": "claude-sonnet-4-20250514"}

    return SubagentEngine(
        parent_tools=tools,
        parent_hooks=hooks,
        parent_permissions=perms,
        parent_provider=provider,
        parent_settings=settings,
    )


async def test_allowed_tools_whitelist():
    """SPAWN-07: allowed_tools restricts child to exactly those tools."""
    engine = _make_engine(
        tool_names=["sql_query", "df_transform", "chart_create", "spawn_agent"],
    )

    child_loop = engine.create_child_loop(
        allowed_tools=["sql_query", "df_transform"],
    )
    child_names = child_loop._tools.names()
    assert set(child_names) == {"sql_query", "df_transform"}


async def test_spawn_agent_excluded_from_whitelist():
    """SPAWN-08: spawn_agent is always excluded even if explicitly listed."""
    engine = _make_engine(
        tool_names=["sql_query", "spawn_agent"],
    )

    child_loop = engine.create_child_loop(
        allowed_tools=["sql_query", "spawn_agent"],
    )
    child_names = child_loop._tools.names()
    assert "spawn_agent" not in child_names
    assert "sql_query" in child_names


async def test_default_inherits_all_except_spawn():
    """When allowed_tools=None, child gets all parent tools except spawn_agent, agent_status, agent_cancel."""
    engine = _make_engine(
        tool_names=[
            "sql_query", "df_transform", "chart_create",
            "spawn_agent", "agent_status", "agent_cancel",
        ],
    )

    child_loop = engine.create_child_loop(allowed_tools=None)
    child_names = set(child_loop._tools.names())

    assert "sql_query" in child_names
    assert "df_transform" in child_names
    assert "chart_create" in child_names
    assert "spawn_agent" not in child_names
    assert "agent_status" not in child_names
    assert "agent_cancel" not in child_names


async def test_child_registry_immutable():
    """SPAWN-09: child and parent registries have independent _tools dicts."""
    engine = _make_engine(tool_names=["sql_query", "df_transform"])

    child_loop = engine.create_child_loop()
    child_registry = child_loop._tools

    # They are different dict objects
    assert child_registry._tools is not engine._parent_tools._tools

    # Adding to parent does not affect child
    engine._parent_tools.register(StubTool("new_tool"))
    assert "new_tool" not in child_registry.names()


async def test_shared_connection_pool():
    """D-05: child tools share the parent's ConnectionPool reference."""
    pool = ConnectionPool()
    parent_sql = SqlQueryTool(pool=pool)

    parent_registry = ToolRegistry()
    parent_registry.register(parent_sql)
    parent_registry.register(StubTool("df_transform"))

    engine = _make_engine(registry=parent_registry)

    child_loop = engine.create_child_loop(allowed_tools=None)
    child_sql = child_loop._tools.get("sql_query")

    # Same ConnectionPool instance (identity check)
    assert child_sql._pool is pool
