# tests/test_subagent/test_lifecycle.py
# Lifecycle tests: foreground (SPAWN-10), background (SPAWN-11), concurrency (SPAWN-12),
# SubagentStop hook (SPAWN-16, D-14), BLOCK ignored (D-13), failure (D-09), notification (D-08).
from unittest.mock import AsyncMock, MagicMock, patch


from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.subagent.manager import SubagentManager
from yigthinker.tools.registry import ToolRegistry
from yigthinker.tools.spawn_agent import SpawnAgentInput, SpawnAgentTool
from yigthinker.types import HookEvent, HookResult


def _make_spawn_tool() -> tuple[SpawnAgentTool, ToolRegistry, HookExecutor, PermissionSystem, AsyncMock]:
    """Build a SpawnAgentTool with mock parent components wired in."""
    tools = ToolRegistry()
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool = SpawnAgentTool()
    tool.set_parent_components(
        tools=tools,
        hooks=hooks,
        permissions=perms,
        provider=provider,
    )
    return tool, tools, hooks, perms, provider


def _make_ctx(settings: dict | None = None) -> SessionContext:
    """Create a SessionContext with spawn_agent settings."""
    s = settings or {"model": "claude-sonnet-4-20250514", "spawn_agent": {"max_concurrent": 3}}
    return SessionContext(settings=s)


async def test_foreground_mode():
    """SPAWN-10: foreground spawn_agent awaits child and returns final text."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hook_registry = HookRegistry()
    hooks = HookExecutor(hook_registry)
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    # Mock SubagentEngine.create_child_loop to return a mock AgentLoop
    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(return_value="Analysis done")

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(prompt="analyze revenue", name="analyst")
        result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert "Analysis done" in result.content
    assert ctx.subagent_manager is not None
    assert ctx.subagent_manager.list_all()[0].status == "completed"


async def test_background_mode():
    """SPAWN-11: background spawn_agent returns immediately with subagent_id."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hook_registry = HookRegistry()
    hooks = HookExecutor(hook_registry)
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(return_value="Background result")

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(prompt="analyze in background", background=True, name="bg-analyst")
        result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert "launched in background" in result.content
    assert ctx.subagent_manager is not None

    # One subagent should be registered
    all_agents = ctx.subagent_manager.list_all()
    assert len(all_agents) == 1
    assert all_agents[0].name == "bg-analyst"
    # Task should exist
    assert all_agents[0].task is not None

    # Wait for the background task to complete
    await all_agents[0].task

    # After task completes, status should be completed
    assert all_agents[0].status == "completed"

    # Notifications should have been added (D-08)
    notifications = ctx.subagent_manager.drain_notifications()
    assert len(notifications) == 1
    assert "bg-analyst" in notifications[0]
    assert "completed" in notifications[0]


async def test_concurrent_limit():
    """SPAWN-12: cannot spawn beyond max_concurrent limit."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx({"model": "test", "spawn_agent": {"max_concurrent": 2}})

    # Manually set up SubagentManager with 2 running subagents
    ctx.subagent_manager = SubagentManager(max_concurrent=2)
    ctx.subagent_manager.register("agent-1")
    ctx.subagent_manager.register("agent-2")

    input_obj = SpawnAgentInput(prompt="should fail")
    result = await tool.execute(input_obj, ctx)

    assert result.is_error
    assert "concurrent subagent limit" in result.content
    assert "(2)" in result.content


async def test_subagent_stop_hook():
    """SPAWN-16 / D-14: SubagentStop hook fires with subagent_final_text populated."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hook_registry = HookRegistry()

    # Track hook calls
    hook_calls: list[HookEvent] = []

    async def capture_hook(event: HookEvent) -> HookResult:
        hook_calls.append(event)
        return HookResult.ALLOW

    hook_registry.register("SubagentStop", "*", capture_hook)
    hooks = HookExecutor(hook_registry)
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(return_value="Revenue is up 15%")

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(prompt="analyze", name="revenue-analyst")
        result = await tool.execute(input_obj, ctx)

    assert not result.is_error

    # Verify SubagentStop was fired
    stop_events = [e for e in hook_calls if e.event_type == "SubagentStop"]
    assert len(stop_events) == 1
    event = stop_events[0]
    assert event.subagent_name == "revenue-analyst"
    assert event.subagent_status == "completed"
    # D-14: subagent_final_text is populated
    assert event.subagent_final_text == "Revenue is up 15%"


async def test_subagent_stop_block_ignored():
    """D-13: SubagentStop BLOCK result is ignored -- tool still succeeds."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hook_registry = HookRegistry()

    # Hook that returns BLOCK
    async def blocking_hook(event: HookEvent) -> HookResult:
        return HookResult.block("should be ignored")

    hook_registry.register("SubagentStop", "*", blocking_hook)
    hooks = HookExecutor(hook_registry)
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(return_value="Success despite block")

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(prompt="test block ignored")
        result = await tool.execute(input_obj, ctx)

    # D-13: Despite hook returning BLOCK, the tool returns successfully
    assert not result.is_error
    assert "Success despite block" in result.content


async def test_foreground_failure():
    """D-09: foreground failure returns ToolResult with is_error=True."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hook_registry = HookRegistry()

    hook_calls: list[HookEvent] = []

    async def capture_hook(event: HookEvent) -> HookResult:
        hook_calls.append(event)
        return HookResult.ALLOW

    hook_registry.register("SubagentStop", "*", capture_hook)
    hooks = HookExecutor(hook_registry)
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(side_effect=Exception("oops something broke"))

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(prompt="will fail", name="failing-agent")
        result = await tool.execute(input_obj, ctx)

    assert result.is_error
    assert "failed" in result.content
    assert "oops something broke" in result.content

    # Manager should show failed status
    assert ctx.subagent_manager is not None
    info = ctx.subagent_manager.list_all()[0]
    assert info.status == "failed"

    # SubagentStop fired with status "failed" and subagent_final_text containing error
    stop_events = [e for e in hook_calls if e.event_type == "SubagentStop"]
    assert len(stop_events) == 1
    assert stop_events[0].subagent_status == "failed"
    assert "oops" in stop_events[0].subagent_final_text


async def test_background_notification():
    """D-08: background subagent completion adds notification via add_notification."""
    tool = SpawnAgentTool()
    tools = ToolRegistry()
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["*"]})
    provider = AsyncMock()

    tool.set_parent_components(tools=tools, hooks=hooks, permissions=perms, provider=provider)
    ctx = _make_ctx()

    mock_child_loop = MagicMock()
    mock_child_loop.run = AsyncMock(return_value="Result from background")

    with patch("yigthinker.tools.spawn_agent.SubagentEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.create_child_loop.return_value = mock_child_loop
        mock_engine_cls.return_value = mock_engine

        input_obj = SpawnAgentInput(
            prompt="background task",
            background=True,
            name="notifier",
        )
        result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert "launched in background" in result.content

    # Wait for background task
    task = ctx.subagent_manager.list_all()[0].task
    await task

    # Drain notifications
    notifications = ctx.subagent_manager.drain_notifications()
    assert len(notifications) == 1
    assert "notifier" in notifications[0]
    assert "Result from background" in notifications[0]


async def test_not_initialized():
    """spawn_agent returns error when parent components not set."""
    tool = SpawnAgentTool()
    ctx = _make_ctx()

    input_obj = SpawnAgentInput(prompt="should fail")
    result = await tool.execute(input_obj, ctx)

    assert result.is_error
    assert "not fully initialized" in result.content
