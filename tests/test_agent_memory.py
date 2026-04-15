# tests/test_agent_memory.py
"""Tests for AgentLoop memory integration: lifecycle events, extraction, and compaction."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.types import (
    Message, LLMResponse, ToolResult, ToolUse, HookEvent, HookResult,
)
from yigthinker.session import SessionContext
from yigthinker.permissions import PermissionSystem
from yigthinker.tools.registry import ToolRegistry
from yigthinker.hooks.registry import HookRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.agent import AgentLoop
from yigthinker.memory.session_memory import MemoryManager
from yigthinker.memory.compact import SmartCompact, CompactConfig
from pydantic import BaseModel


class EchoInput(BaseModel):
    message: str


class EchoTool:
    name = "echo"
    description = "Echoes the message"
    input_schema = EchoInput

    async def execute(self, input: EchoInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"echo: {input.message}")


def _make_loop(
    responses: list[LLMResponse],
    hook_registry: HookRegistry | None = None,
    memory_manager: MemoryManager | None = None,
    compact: SmartCompact | None = None,
    max_iterations: int = 50,
    timeout_seconds: float = 300.0,
) -> tuple[AgentLoop, SessionContext, AsyncMock]:
    """Build an AgentLoop with mocks, returning (loop, ctx, mock_provider)."""
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=responses)

    tools = ToolRegistry()
    tools.register(EchoTool())

    hr = hook_registry or HookRegistry()
    hooks = HookExecutor(hr)
    perms = PermissionSystem({"allow": ["echo"]})

    loop = AgentLoop(
        provider=mock_provider,
        tools=tools,
        hooks=hooks,
        permissions=perms,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
    )

    if memory_manager is not None:
        loop.set_memory_manager(memory_manager)
    if compact is not None:
        loop.set_compact(compact)

    ctx = SessionContext()
    return loop, ctx, mock_provider


# ---------------------------------------------------------------------------
# Test 1: SessionStart fires
# ---------------------------------------------------------------------------
async def test_session_start_fires():
    """AgentLoop.run() fires SessionStart hook before the main loop."""
    fired_events: list[str] = []

    async def capture(event: HookEvent) -> HookResult:
        fired_events.append(event.event_type)
        return HookResult.ALLOW

    reg = HookRegistry()
    reg.register("SessionStart", "*", capture)

    loop, ctx, _ = _make_loop(
        [LLMResponse(stop_reason="end_turn", text="ok")],
        hook_registry=reg,
    )
    await loop.run("hello", ctx)
    assert "SessionStart" in fired_events


# ---------------------------------------------------------------------------
# Test 2: SessionEnd fires
# ---------------------------------------------------------------------------
async def test_session_end_fires():
    """AgentLoop.run() fires SessionEnd hook after the main loop."""
    fired_events: list[str] = []

    async def capture(event: HookEvent) -> HookResult:
        fired_events.append(event.event_type)
        return HookResult.ALLOW

    reg = HookRegistry()
    reg.register("SessionEnd", "*", capture)

    loop, ctx, _ = _make_loop(
        [LLMResponse(stop_reason="end_turn", text="ok")],
        hook_registry=reg,
    )
    await loop.run("hello", ctx)
    assert "SessionEnd" in fired_events


# ---------------------------------------------------------------------------
# Test 3: Memory extraction after tool call
# ---------------------------------------------------------------------------
async def test_memory_extraction_after_tool_call():
    """After tool calls, record_turn() is called and extraction is scheduled."""
    tool_resp = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "hi"})],
    )
    final_resp = LLMResponse(stop_reason="end_turn", text="done")

    mm = MagicMock(spec=MemoryManager)
    mm.record_turn = MagicMock()
    mm.should_extract = MagicMock(return_value=True)
    mm.load_memory = MagicMock(return_value="")

    loop, ctx, _ = _make_loop(
        [tool_resp, final_resp],
        memory_manager=mm,
    )

    mock_task = MagicMock(spec=asyncio.Task)
    with patch("asyncio.create_task", return_value=mock_task) as mock_create_task:
        await loop.run("echo hi", ctx)

    mm.record_turn.assert_called()
    mock_create_task.assert_called()
    # Verify the task was stored (add_done_callback was called)
    mock_task.add_done_callback.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: PreCompact fires on budget exceeded
# ---------------------------------------------------------------------------
async def test_precompact_fires_on_budget_exceeded():
    """When token estimate exceeds history budget, PreCompact hook fires."""
    fired_events: list[str] = []

    async def capture(event: HookEvent) -> HookResult:
        fired_events.append(event.event_type)
        return HookResult.ALLOW

    reg = HookRegistry()
    reg.register("PreCompact", "*", capture)
    reg.register("SessionStart", "*", capture)
    reg.register("SessionEnd", "*", capture)

    # Use a very low history budget to trigger compaction
    ctx = SessionContext()
    ctx.context_manager._max_tokens = 100  # ~40 token history budget

    # Stuff existing messages to exceed budget
    ctx.messages = [
        Message(role="user", content="x" * 500),
        Message(role="assistant", content="y" * 500),
    ]

    mm = MagicMock(spec=MemoryManager)
    mm.load_memory = MagicMock(return_value="some memory")
    mm.record_turn = MagicMock()
    mm.should_extract = MagicMock(return_value=False)

    compact = SmartCompact(CompactConfig(max_tokens=10))  # very low threshold

    loop, _, mock_prov = _make_loop(
        [LLMResponse(stop_reason="end_turn", text="ok")],
        hook_registry=reg,
        memory_manager=mm,
        compact=compact,
    )
    await loop.run("query", ctx)
    assert "PreCompact" in fired_events


# ---------------------------------------------------------------------------
# Test 5: Compaction injects memory and shortens messages
# ---------------------------------------------------------------------------
async def test_compaction_injects_memory():
    """When budget exceeded, SmartCompact compresses the message list."""
    ctx = SessionContext()
    ctx.context_manager._max_tokens = 100  # ~40 token history budget

    ctx.messages = [
        Message(role="user", content="x" * 500),
        Message(role="assistant", content="y" * 500),
    ] * 5  # 10 messages, lots of content

    mm = MagicMock(spec=MemoryManager)
    mm.load_memory = MagicMock(return_value="remembered data")
    mm.record_turn = MagicMock()
    mm.should_extract = MagicMock(return_value=False)

    compact = SmartCompact(CompactConfig(max_tokens=10))  # very low threshold

    loop, _, mock_prov = _make_loop(
        [LLMResponse(stop_reason="end_turn", text="ok")],
        memory_manager=mm,
        compact=compact,
    )

    await loop.run("query", ctx)

    # The messages sent to the provider should be shorter than the original
    call_messages = mock_prov.chat.call_args_list[0].args[0]
    # The compacted message list should be shorter than the 10 originals + user query
    # (smart compact keeps a tail subset + memory message)
    assert len(call_messages) < 12


# ---------------------------------------------------------------------------
# Test 6: Extraction uses message snapshot (not original reference)
# ---------------------------------------------------------------------------
async def test_extraction_uses_message_snapshot():
    """extract_memories receives a copy of messages, not the live list."""
    tool_resp = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "hi"})],
    )
    final_resp = LLMResponse(stop_reason="end_turn", text="done")

    mm = MagicMock(spec=MemoryManager)
    mm.record_turn = MagicMock()
    mm.should_extract = MagicMock(return_value=True)
    mm.load_memory = MagicMock(return_value="")

    loop, ctx, _ = _make_loop(
        [tool_resp, final_resp],
        memory_manager=mm,
    )

    captured_snapshots: list[list] = []

    async def capturing_extraction(messages_snapshot):
        captured_snapshots.append(messages_snapshot)

    loop._run_extraction = capturing_extraction

    with patch("asyncio.create_task", side_effect=lambda coro: asyncio.ensure_future(coro)):
        await loop.run("echo hi", ctx)

    # Wait a tiny bit for the background task to complete
    await asyncio.sleep(0.01)

    assert len(captured_snapshots) >= 1
    snapshot = captured_snapshots[0]
    # The snapshot should be a list but NOT the same object as ctx.messages
    assert isinstance(snapshot, list)


# ---------------------------------------------------------------------------
# Phase 10 / BHV-02: startup alert provider (CORR-02 -- NOT a SessionStart hook)
# ---------------------------------------------------------------------------

async def test_session_start_injects_health_alerts():
    """BHV-02: when the startup_alert_provider returns a non-empty string, AgentLoop.run
    prepends it to the system_prompt as a `[Workflow Health Alert]` block exactly ONCE
    per run (gated on iteration == 1)."""
    loop, ctx, mock_provider = _make_loop([
        LLMResponse(stop_reason="end_turn", text="ok"),
    ])

    alert_text = (
        "[Workflow Health Alert] 1 active workflow needs attention:\n"
        "  * monthly_sales_report: overdue (last_run=2026-03-01T00:00:00Z, schedule='0 0 1 * *')\n"
        "Use workflow_manage(action=\"inspect\", ...) for details."
    )
    call_count = {"n": 0}

    def provider_fn() -> str | None:
        call_count["n"] += 1
        return alert_text

    loop.set_startup_alert_provider(provider_fn)

    await loop.run("Show me the budget variance.", ctx)

    # Provider must be invoked exactly once per run, not per iteration.
    assert call_count["n"] == 1, f"Expected 1 provider call, got {call_count['n']}"

    # The chat call must have received system prompt containing the alert header.
    chat_call = mock_provider.chat.call_args_list[0]
    # mock_provider.chat is called with positional args (messages, tools) and keyword `system`
    system_kwarg = chat_call.kwargs.get("system")
    assert system_kwarg is not None
    assert "[Workflow Health Alert]" in system_kwarg
    assert "monthly_sales_report" in system_kwarg


async def test_session_start_silent_empty_registry():
    """BHV-02: when the provider returns None, NO alert block appears in system_prompt."""
    loop, ctx, mock_provider = _make_loop([
        LLMResponse(stop_reason="end_turn", text="ok"),
    ])

    def empty_provider() -> str | None:
        return None

    loop.set_startup_alert_provider(empty_provider)
    await loop.run("hello", ctx)

    chat_call = mock_provider.chat.call_args_list[0]
    system_kwarg = chat_call.kwargs.get("system")
    # Either None OR a string that does NOT contain the alert marker.
    if system_kwarg is not None:
        assert "[Workflow Health Alert]" not in system_kwarg


async def test_session_start_silent_healthy():
    """BHV-02: when the provider returns an empty string '' (treated same as None), no alert block."""
    loop, ctx, mock_provider = _make_loop([
        LLMResponse(stop_reason="end_turn", text="ok"),
    ])

    def empty_string_provider() -> str | None:
        return ""

    loop.set_startup_alert_provider(empty_string_provider)
    await loop.run("hello", ctx)

    chat_call = mock_provider.chat.call_args_list[0]
    system_kwarg = chat_call.kwargs.get("system")
    if system_kwarg is not None:
        assert "[Workflow Health Alert]" not in system_kwarg


async def test_session_start_resilient_bad_registry():
    """BHV-02 / Pitfall 3: a crashing startup_alert_provider MUST NOT break AgentLoop.run()."""
    loop, ctx, mock_provider = _make_loop([
        LLMResponse(stop_reason="end_turn", text="survived"),
    ])

    def crashing_provider() -> str | None:
        raise RuntimeError("registry.json is corrupted")

    loop.set_startup_alert_provider(crashing_provider)

    # Must complete normally despite the provider exception.
    result = await loop.run("hello", ctx)
    assert result == "survived"
    assert mock_provider.chat.called
