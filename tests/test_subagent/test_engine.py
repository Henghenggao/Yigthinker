# tests/test_subagent/test_engine.py
# Unit tests for SubagentEngine and SubagentManager (SPAWN-01..03, 08, 15, 16, D-06, D-14)
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.subagent.engine import SubagentEngine
from yigthinker.subagent.manager import SubagentInfo, SubagentManager
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import HookEvent, ToolResult


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
    settings: dict | None = None,
) -> SubagentEngine:
    """Build a SubagentEngine with mock parent components."""
    tools = ToolRegistry()
    for name in (tool_names or ["sql_query", "df_transform"]):
        tools.register(StubTool(name))

    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["sql_query", "df_transform"]})
    provider = AsyncMock()
    s = settings or {"model": "claude-sonnet-4-20250514"}

    return SubagentEngine(
        parent_tools=tools,
        parent_hooks=hooks,
        parent_permissions=perms,
        parent_provider=provider,
        parent_settings=s,
    )


# ---------------------------------------------------------------------------
# SubagentEngine tests
# ---------------------------------------------------------------------------

async def test_child_has_isolated_context():
    """SPAWN-01: child AgentLoop gets isolated SessionContext with empty messages."""
    engine = _make_engine()
    child_loop = engine.create_child_loop()

    # The child loop is a real AgentLoop instance
    from yigthinker.agent import AgentLoop
    assert isinstance(child_loop, AgentLoop)

    # Create a child context -- it should have empty messages and fresh VarRegistry
    child_ctx = SessionContext()
    assert child_ctx.messages == []
    assert child_ctx.vars.list() == []


async def test_only_final_text_returned():
    """SPAWN-02: child AgentLoop.run() returns only the final text string."""
    engine = _make_engine()
    child_loop = engine.create_child_loop()

    # Mock the provider to return a direct end_turn
    from yigthinker.types import LLMResponse
    child_loop._provider.chat = AsyncMock(
        return_value=LLMResponse(stop_reason="end_turn", text="Analysis complete")
    )

    child_ctx = SessionContext()
    result = await child_loop.run("analyze data", child_ctx)
    assert result == "Analysis complete"


async def test_model_override():
    """SPAWN-03: model override creates a different provider via provider_from_settings."""
    engine = _make_engine(settings={"model": "claude-sonnet-4-20250514"})

    with patch("yigthinker.subagent.engine.provider_from_settings") as mock_pfs:
        mock_provider = AsyncMock()
        mock_pfs.return_value = mock_provider

        child_loop = engine.create_child_loop(model="gpt-4o")

        # provider_from_settings was called with settings containing model="gpt-4o"
        mock_pfs.assert_called_once()
        call_settings = mock_pfs.call_args.args[0]
        assert call_settings["model"] == "gpt-4o"

        # The child loop uses the returned provider
        assert child_loop._provider is mock_provider

    # When model=None, parent provider is used
    child_loop_default = engine.create_child_loop(model=None)
    assert child_loop_default._provider is engine._parent_provider


async def test_hook_inheritance():
    """SPAWN-15: child AgentLoop receives same HookExecutor and PermissionSystem."""
    engine = _make_engine()
    child_loop = engine.create_child_loop()

    # Same instances (identity check)
    assert child_loop._hooks is engine._parent_hooks
    assert child_loop._permissions is engine._parent_permissions


async def test_spawn_agent_excluded_from_child():
    """SPAWN-08 / D-06: spawn_agent is always excluded from child ToolRegistry."""
    engine = _make_engine(
        tool_names=["sql_query", "spawn_agent", "df_transform"],
    )

    # No allowed_tools filter -- spawn_agent still excluded
    child_loop = engine.create_child_loop()
    child_tool_names = child_loop._tools.names()
    assert "spawn_agent" not in child_tool_names
    assert "sql_query" in child_tool_names
    assert "df_transform" in child_tool_names

    # With explicit allowed_tools including spawn_agent -- still excluded
    child_loop2 = engine.create_child_loop(allowed_tools=["sql_query", "spawn_agent"])
    child_tool_names2 = child_loop2._tools.names()
    assert "spawn_agent" not in child_tool_names2
    assert "sql_query" in child_tool_names2


async def test_agent_status_cancel_excluded_from_child():
    """agent_status and agent_cancel are parent-only management tools."""
    engine = _make_engine(
        tool_names=["sql_query", "agent_status", "agent_cancel", "df_transform"],
    )

    child_loop = engine.create_child_loop()
    child_tool_names = child_loop._tools.names()
    assert "agent_status" not in child_tool_names
    assert "agent_cancel" not in child_tool_names
    assert "sql_query" in child_tool_names


async def test_child_ask_fn_is_none():
    """Children never prompt user: ask_fn must be None."""
    engine = _make_engine()
    child_loop = engine.create_child_loop()
    assert child_loop._ask_fn is None


async def test_child_iteration_and_timeout_defaults():
    """Default max_iterations=20, timeout=120 per D-19/D-07/D-20."""
    engine = _make_engine()
    child_loop = engine.create_child_loop()
    assert child_loop._max_iterations == 20
    assert child_loop._timeout_seconds == 120.0


async def test_child_iteration_and_timeout_from_settings():
    """spawn_agent config overrides iteration and timeout defaults."""
    engine = _make_engine(settings={
        "model": "claude-sonnet-4-20250514",
        "spawn_agent": {"max_iterations": 10, "timeout": 60.0},
    })
    child_loop = engine.create_child_loop()
    assert child_loop._max_iterations == 10
    assert child_loop._timeout_seconds == 60.0


# ---------------------------------------------------------------------------
# SubagentManager tests
# ---------------------------------------------------------------------------

def test_manager_can_spawn():
    """Concurrency limit: can_spawn returns True when under limit, False at limit."""
    mgr = SubagentManager(max_concurrent=2)
    assert mgr.can_spawn() is True

    mgr.register("agent-1")
    assert mgr.can_spawn() is True

    mgr.register("agent-2")
    assert mgr.can_spawn() is False


def test_manager_register_and_list():
    """register() creates SubagentInfo, list_all() returns it."""
    mgr = SubagentManager()
    info = mgr.register("east-region")

    assert isinstance(info, SubagentInfo)
    assert info.name == "east-region"
    assert info.status == "running"

    all_agents = mgr.list_all()
    assert len(all_agents) == 1
    assert all_agents[0] is info


def test_manager_complete_and_fail():
    """complete() and fail() update status and final_text."""
    mgr = SubagentManager()
    info = mgr.register("agent-a")

    mgr.complete(info.subagent_id, "Analysis done")
    assert info.status == "completed"
    assert info.final_text == "Analysis done"

    info2 = mgr.register("agent-b")
    mgr.fail(info2.subagent_id, "timeout error")
    assert info2.status == "failed"
    assert info2.final_text == "timeout error"


def test_manager_cancel():
    """cancel() sets status to cancelled and calls task.cancel()."""
    mgr = SubagentManager()
    mock_task = MagicMock(spec=asyncio.Task)
    info = mgr.register("cancellable", task=mock_task)

    result = mgr.cancel(info.subagent_id)
    assert result is True
    assert info.status == "cancelled"
    mock_task.cancel.assert_called_once()


def test_manager_cancel_no_task():
    """cancel() returns False when there is no task to cancel."""
    mgr = SubagentManager()
    info = mgr.register("no-task")  # task=None by default

    result = mgr.cancel(info.subagent_id)
    assert result is False


def test_manager_cancel_already_completed():
    """cancel() returns False for non-running subagents."""
    mgr = SubagentManager()
    mock_task = MagicMock(spec=asyncio.Task)
    info = mgr.register("done-agent", task=mock_task)
    mgr.complete(info.subagent_id, "done")

    result = mgr.cancel(info.subagent_id)
    assert result is False


def test_manager_get():
    """get() retrieves by subagent_id, returns None for unknown id."""
    mgr = SubagentManager()
    info = mgr.register("findme")

    assert mgr.get(info.subagent_id) is info
    assert mgr.get("nonexistent") is None


def test_manager_drain_notifications():
    """add_notification() queues messages, drain_notifications() returns and clears."""
    mgr = SubagentManager()
    mgr.add_notification("agent-1 completed")
    mgr.add_notification("agent-2 failed")

    drained = mgr.drain_notifications()
    assert drained == ["agent-1 completed", "agent-2 failed"]

    # Second drain should be empty
    assert mgr.drain_notifications() == []


async def test_manager_shutdown():
    """shutdown() cancels all running subagents."""
    mgr = SubagentManager()
    task1 = MagicMock(spec=asyncio.Task)
    task2 = MagicMock(spec=asyncio.Task)

    mgr.register("agent-1", task=task1)
    info2 = mgr.register("agent-2", task=task2)
    mgr.complete(info2.subagent_id, "done")  # already completed

    await mgr.shutdown()

    task1.cancel.assert_called_once()
    task2.cancel.assert_not_called()  # already completed


# ---------------------------------------------------------------------------
# SubagentStop HookEvent test
# ---------------------------------------------------------------------------

def test_subagent_stop_event():
    """SPAWN-16 / D-14: HookEvent supports SubagentStop with subagent_final_text."""
    event = HookEvent(
        event_type="SubagentStop",
        session_id="test-session",
        transcript_path="",
        subagent_id="abc-123",
        subagent_name="east-analyst",
        subagent_status="completed",
        subagent_final_text="Analysis summary: revenue up 15%",
    )

    assert event.event_type == "SubagentStop"
    assert event.subagent_id == "abc-123"
    assert event.subagent_name == "east-analyst"
    assert event.subagent_status == "completed"
    assert event.subagent_final_text == "Analysis summary: revenue up 15%"
