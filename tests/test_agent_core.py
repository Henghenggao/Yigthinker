# tests/test_agent.py
import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from yigthinker.types import Message, LLMResponse, StreamEvent, ToolResult, ToolUse, HookResult
from yigthinker.session import SessionContext
from yigthinker.permissions import PermissionSystem
from yigthinker.tools.registry import ToolRegistry
from yigthinker.hooks.registry import HookRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.agent import AgentLoop, MAX_RESULT_CHARS


class EchoInput(BaseModel):
    message: str


class EchoTool:
    name = "echo"
    description = "Echoes the message"
    input_schema = EchoInput

    async def execute(self, input: EchoInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"echo: {input.message}")


def make_loop(
    responses: list[LLMResponse],
    allow_all: bool = True,
    max_iterations: int = 50,
    timeout_seconds: float = 300.0,
) -> tuple[AgentLoop, SessionContext]:
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=responses)

    tools = ToolRegistry()
    tools.register(EchoTool())

    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]} if allow_all else {})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=max_iterations, timeout_seconds=timeout_seconds,
    )
    ctx = SessionContext()
    return loop, ctx


async def test_end_turn_returns_text():
    loop, ctx = make_loop([LLMResponse(stop_reason="end_turn", text="Done")])
    result = await loop.run("hello", ctx)
    assert result == "Done"


async def test_tool_use_then_end_turn():
    tool_response = LLMResponse(
        stop_reason="tool_use",
        text="",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "world"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Echoed: world")

    loop, ctx = make_loop([tool_response, final_response])
    result = await loop.run("echo world", ctx)
    assert result == "Echoed: world"


async def test_denied_tool_returns_error_to_llm():
    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "hi"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Permission denied handled")

    loop, ctx = make_loop([tool_response, final_response], allow_all=False)
    result = await loop.run("echo hi", ctx)
    assert result == "Permission denied handled"


async def test_hook_block_returns_error_to_llm():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="echo")
    async def blocker(event):
        return HookResult.block("blocked by hook")

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "hi"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Hook block handled")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])
    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(reg)
    perms = PermissionSystem({"allow": ["echo"]})

    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()
    result = await loop.run("echo hi", ctx)
    assert result == "Hook block handled"


async def test_session_messages_persist_across_turns():
    first = LLMResponse(stop_reason="end_turn", text="First reply")
    second = LLMResponse(stop_reason="end_turn", text="Second reply")
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[first, second])

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    await loop.run("first", ctx)
    await loop.run("second", ctx)

    second_call_messages = mock_provider.chat.await_args_list[1].args[0]
    assert any(message.content == "First reply" for message in second_call_messages)


async def test_iteration_limit_graceful_stop():
    """When max_iterations is exceeded, LLM is asked to summarize with no tools."""
    # Create 3 tool_use responses (consuming the limit of 3) + 1 summary for graceful stop
    tool_responses = [
        LLMResponse(
            stop_reason="tool_use",
            tool_uses=[ToolUse(id=f"tu{i}", name="echo", input={"message": "hi"})],
        )
        for i in range(3)
    ]
    summary = LLMResponse(stop_reason="end_turn", text="Here is my summary")
    all_responses = tool_responses + [summary]

    loop, ctx = make_loop(all_responses, max_iterations=3)
    result = await loop.run("do lots of stuff", ctx)
    assert result == "Here is my summary"

    # The summary call should have been made with empty tools list
    last_call = loop._provider.chat.await_args_list[-1]
    assert last_call.args[1] == []  # tools param is empty


async def test_timeout_returns_partial():
    """When timeout is hit, a timeout message is returned."""
    import asyncio

    async def slow_chat(messages, tools, **kwargs):
        await asyncio.sleep(10)  # way past timeout
        return LLMResponse(stop_reason="end_turn", text="should not reach")

    mock_provider = AsyncMock()
    mock_provider.chat = slow_chat

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=50, timeout_seconds=0.1,
    )
    ctx = SessionContext()
    result = await loop.run("hello", ctx)
    assert "timed out" in result.lower()


async def test_tool_exception_reported_to_llm():
    """When a tool raises, error is reported as tool_result with is_error=True."""
    class FailInput(BaseModel):
        message: str

    class FailTool:
        name = "fail"
        description = "Always fails"
        input_schema = FailInput
        async def execute(self, input, ctx):
            raise RuntimeError("tool exploded")

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="fail", input={"message": "boom"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Handled the error")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])
    tools = ToolRegistry()
    tools.register(FailTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["fail"]})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
    )
    ctx = SessionContext()
    result = await loop.run("do it", ctx)
    assert result == "Handled the error"

    # Verify the error was passed in tool_results
    # The second chat call receives messages ending with: [... assistant(tool_use), user(tool_results)]
    second_call_messages = mock_provider.chat.await_args_list[1].args[0]
    # Find the tool_results message (user message with list content containing tool_result dicts)
    tool_result_msgs = [
        m for m in second_call_messages
        if m.role == "user" and isinstance(m.content, list)
    ]
    assert len(tool_result_msgs) > 0
    tool_result_msg = tool_result_msgs[-1]
    assert any(
        "tool exploded" in str(item.get("content", ""))
        for item in tool_result_msg.content
        if isinstance(item, dict) and item.get("type") == "tool_result"
    )


async def test_tool_result_dicts_are_serialized_as_json():
    class ChartInput(BaseModel):
        name: str

    class ChartTool:
        name = "chart"
        description = "Returns chart payload"
        input_schema = ChartInput

        async def execute(self, input, ctx):
            return ToolResult(
                tool_use_id="",
                content={"chart_name": input.name, "chart_json": '{"data":[],"layout":{}}'},
            )

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="chart", input={"name": "last_chart"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="done")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])
    tools = ToolRegistry()
    tools.register(ChartTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["chart"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    await loop.run("make a chart", ctx)

    second_call_messages = mock_provider.chat.await_args_list[1].args[0]
    tool_result_msg = next(
        m for m in second_call_messages
        if m.role == "user" and isinstance(m.content, list)
    )
    payload = next(
        item["content"]
        for item in tool_result_msg.content
        if isinstance(item, dict) and item.get("type") == "tool_result"
    )
    assert payload == '{"chart_name": "last_chart", "chart_json": "{\\"data\\":[],\\"layout\\":{}}"}'


# ---------------------------------------------------------------------------
# Streaming Tests
# ---------------------------------------------------------------------------

async def _mock_stream(*events):
    """Helper: create an async generator that yields StreamEvent objects."""
    for e in events:
        yield e


async def test_streaming_callback_fires_per_token():
    """When on_token is provided, AgentLoop uses stream() and fires callback per chunk."""
    mock_provider = AsyncMock()
    mock_provider.stream = MagicMock(return_value=_mock_stream(
        StreamEvent(type="text", text="Hello"),
        StreamEvent(type="text", text=" world"),
        StreamEvent(type="done", stop_reason="end_turn"),
    ))
    # chat should not be called in the streaming path
    mock_provider.chat = AsyncMock(side_effect=AssertionError("chat should not be called"))

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    on_token_calls: list[str] = []
    result = await loop.run("hi", ctx, on_token=lambda t: on_token_calls.append(t))

    assert on_token_calls == ["Hello", " world"]
    assert result == "Hello world"


async def test_streaming_with_tool_use():
    """Streaming path handles tool_use: stream -> tool exec -> stream again."""
    # First turn: text + tool_use
    first_stream = _mock_stream(
        StreamEvent(type="text", text="Let me check"),
        StreamEvent(type="tool_use", tool_use=ToolUse(id="tu1", name="echo", input={"message": "hi"})),
        StreamEvent(type="done", stop_reason="tool_use"),
    )
    # Second turn: final text
    second_stream = _mock_stream(
        StreamEvent(type="text", text="Done"),
        StreamEvent(type="done", stop_reason="end_turn"),
    )

    mock_provider = AsyncMock()
    mock_provider.stream = MagicMock(side_effect=[first_stream, second_stream])
    mock_provider.chat = AsyncMock(side_effect=AssertionError("chat should not be called"))

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    on_token_calls: list[str] = []
    result = await loop.run("echo hi", ctx, on_token=lambda t: on_token_calls.append(t))

    assert result == "Done"
    assert "Let me check" in on_token_calls
    assert "Done" in on_token_calls


async def test_no_streaming_when_on_token_none():
    """When on_token is None, AgentLoop uses chat() and never calls stream()."""
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(return_value=LLMResponse(stop_reason="end_turn", text="Result"))

    def fail_stream(*args, **kwargs):
        raise AssertionError("stream should not be called")

    mock_provider.stream = fail_stream

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("hello", ctx)
    assert result == "Result"


# ---------------------------------------------------------------------------
# Concurrent Execution Tests
# ---------------------------------------------------------------------------


class SlowSafeInput(BaseModel):
    message: str


class SlowSafeTool:
    name = "slow_safe"
    description = "Slow but concurrency-safe tool"
    input_schema = SlowSafeInput
    is_concurrency_safe = True

    def __init__(self):
        self.start_times: list[float] = []
        self.end_times: list[float] = []

    async def execute(self, input: SlowSafeInput, ctx: SessionContext) -> ToolResult:
        self.start_times.append(time.monotonic())
        await asyncio.sleep(0.1)
        self.end_times.append(time.monotonic())
        return ToolResult(tool_use_id="", content=f"safe: {input.message}")


class SlowSafeTool2:
    name = "slow_safe2"
    description = "Another slow safe tool"
    input_schema = SlowSafeInput
    is_concurrency_safe = True

    def __init__(self):
        self.start_times: list[float] = []
        self.end_times: list[float] = []

    async def execute(self, input: SlowSafeInput, ctx: SessionContext) -> ToolResult:
        self.start_times.append(time.monotonic())
        await asyncio.sleep(0.1)
        self.end_times.append(time.monotonic())
        return ToolResult(tool_use_id="", content=f"safe2: {input.message}")


class UnsafeTool:
    name = "unsafe_tool"
    description = "Unsafe tool (no concurrency)"
    input_schema = SlowSafeInput

    def __init__(self):
        self.call_count = 0

    async def execute(self, input: SlowSafeInput, ctx: SessionContext) -> ToolResult:
        self.call_count += 1
        return ToolResult(tool_use_id="", content=f"unsafe: {input.message}")


async def test_concurrent_tool_execution():
    """Two concurrency-safe tools should run in parallel (overlapping execution)."""
    safe1 = SlowSafeTool()
    safe2 = SlowSafeTool2()

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[
            ToolUse(id="tu1", name="slow_safe", input={"message": "a"}),
            ToolUse(id="tu2", name="slow_safe2", input={"message": "b"}),
        ],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Done")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])

    tools = ToolRegistry()
    tools.register(safe1)
    tools.register(safe2)
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["slow_safe", "slow_safe2"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("do both", ctx)
    assert result == "Done"

    # Both tools started before either finished (overlapping execution)
    assert len(safe1.start_times) == 1
    assert len(safe2.start_times) == 1
    # Both started before max end time of either — they overlapped
    max_start = max(safe1.start_times[0], safe2.start_times[0])
    min_end = min(safe1.end_times[0], safe2.end_times[0])
    # If they ran sequentially, max_start would be >= min_end
    # If concurrent, max_start < min_end (both started before either finished)
    assert max_start < min_end, "Tools did not run concurrently"


async def test_concurrent_mixed_safe_unsafe():
    """Mixed batch: safe tools run concurrently, unsafe serially, result order preserved."""
    safe1 = SlowSafeTool()
    safe2 = SlowSafeTool2()
    unsafe = UnsafeTool()

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[
            ToolUse(id="tu1", name="slow_safe", input={"message": "a"}),
            ToolUse(id="tu2", name="unsafe_tool", input={"message": "b"}),
            ToolUse(id="tu3", name="slow_safe2", input={"message": "c"}),
        ],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Mixed done")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])

    tools = ToolRegistry()
    tools.register(safe1)
    tools.register(safe2)
    tools.register(unsafe)
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["slow_safe", "slow_safe2", "unsafe_tool"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("do all", ctx)
    assert result == "Mixed done"

    # Verify result ordering matches original tool_use order
    second_call = mock_provider.chat.await_args_list[1].args[0]
    tool_results_msg = [m for m in second_call if m.role == "user" and isinstance(m.content, list)][-1]
    ids = [item["tool_use_id"] for item in tool_results_msg.content if isinstance(item, dict)]
    assert ids == ["tu1", "tu2", "tu3"]

    # Verify all tools were called
    assert len(safe1.start_times) == 1
    assert len(safe2.start_times) == 1
    assert unsafe.call_count == 1


# ---------------------------------------------------------------------------
# Result Truncation Tests
# ---------------------------------------------------------------------------


async def test_result_truncation():
    """Tool result > MAX_RESULT_CHARS is truncated with informative suffix."""
    class BigInput(BaseModel):
        size: int

    class BigTool:
        name = "big"
        description = "Returns big result"
        input_schema = BigInput

        async def execute(self, input, ctx):
            return ToolResult(tool_use_id="", content="x" * input.size)

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="big", input={"size": 20000})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Done")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])
    tools = ToolRegistry()
    tools.register(BigTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["big"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    await loop.run("big result", ctx)

    second_call = mock_provider.chat.await_args_list[1].args[0]
    tool_results_msg = [m for m in second_call if m.role == "user" and isinstance(m.content, list)][-1]
    content = tool_results_msg.content[0]["content"]
    assert "truncated" in content
    assert "20000" in content
    # Content should be truncated to MAX_RESULT_CHARS + suffix
    assert content.startswith("x" * MAX_RESULT_CHARS)


async def test_result_no_truncation_under_limit():
    """Tool result under MAX_RESULT_CHARS is not truncated."""
    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "short"})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Done")

    loop, ctx = make_loop([tool_response, final_response])
    await loop.run("echo", ctx)

    second_call = loop._provider.chat.await_args_list[1].args[0]
    tool_results_msg = [m for m in second_call if m.role == "user" and isinstance(m.content, list)][-1]
    content = tool_results_msg.content[0]["content"]
    assert "truncated" not in content
    assert content == "echo: short"


# ---------------------------------------------------------------------------
# Fallback Provider Tests
# ---------------------------------------------------------------------------


async def test_fallback_provider_on_error():
    """When primary provider fails, fallback is used and returns successfully."""
    primary = AsyncMock()
    primary.chat = AsyncMock(side_effect=RuntimeError("primary down"))

    fallback = AsyncMock()
    fallback.chat = AsyncMock(return_value=LLMResponse(stop_reason="end_turn", text="fallback result"))

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=primary, tools=tools, hooks=hooks, permissions=perms,
        fallback_provider=fallback,
    )
    ctx = SessionContext()

    result = await loop.run("do it", ctx)
    assert result == "fallback result"
    assert fallback.chat.await_count == 1


async def test_no_fallback_when_none():
    """When no fallback is configured, primary exception propagates."""
    primary = AsyncMock()
    primary.chat = AsyncMock(side_effect=RuntimeError("primary down"))

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=primary, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    with pytest.raises(RuntimeError, match="primary down"):
        await loop.run("do it", ctx)


# ---------------------------------------------------------------------------
# Microcompact Tests
# ---------------------------------------------------------------------------


async def test_microcompact_replaces_old_results():
    """_microcompact replaces old tool_result contents that have been referenced."""
    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=AsyncMock(), tools=tools, hooks=hooks, permissions=perms,
    )

    messages = [
        # Message 0: user input
        Message(role="user", content="initial"),
        # Message 1: assistant with tool_use (references tu_old)
        Message(role="assistant", content=[
            {"type": "tool_use", "id": "tu_old", "name": "echo", "input": {"message": "hi"}},
        ]),
        # Message 2: tool_result (the one that should be replaced)
        Message(role="user", content=[
            {"type": "tool_result", "tool_use_id": "tu_old", "content": "very long result " * 100, "is_error": False},
        ]),
        # Message 3: assistant text
        Message(role="assistant", content="Based on the echo result..."),
        # Message 4: user follow-up
        Message(role="user", content="follow up"),
        # Message 5: assistant referencing tu_old again
        Message(role="assistant", content=[
            {"type": "tool_use", "id": "tu_old", "name": "echo", "input": {"message": "ref"}},
        ]),
        # Message 6: another result
        Message(role="user", content=[
            {"type": "tool_result", "tool_use_id": "tu_old", "content": "another result", "is_error": False},
        ]),
    ]

    result = loop._microcompact(messages)

    # The old tool_result at index 2 should be replaced (it's > 3 msgs from end)
    old_result = result[2].content[0]
    assert old_result["content"] == "[result referenced - omitted for context efficiency]"

    # The recent tool_result at index 6 should NOT be replaced (within last 3 messages)
    recent_result = result[6].content[0]
    assert recent_result["content"] == "another result"


# ─── quick-260416-j3y-04: soft deadline + partial vars + per-channel override ───


async def test_soft_deadline_message_injected_once_when_budget_fraction_crossed():
    """At 80% of the wall-clock budget, the agent must prepend ONE system-style
    steering message so the LLM wraps up instead of being killed mid-iteration.

    Timing strategy: budget 1.0s, 80% deadline = 0.8s.
      - call 1: tool_use, sleeps 0.85s  → elapsed crosses 0.8s during call 1
      - call 2: end_turn, near-instant  → injection must fire exactly before
                                          this call, and the run should finish
                                          inside the 1.0s budget.
    """
    from yigthinker.agent import _SOFT_DEADLINE_MSG

    tu_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="echo", input={"message": "a"})],
    )
    end_response = LLMResponse(stop_reason="end_turn", text="done")

    captured_messages: list[list[Message]] = []
    call_count = 0

    async def slow_chat(messages, tools, **kwargs):
        nonlocal call_count
        captured_messages.append(list(messages))
        call_count += 1
        if call_count == 1:
            # Crosses the 80% mark during this call.
            await asyncio.sleep(0.85)
            return tu_response
        # Call 2+: fast end_turn so the run completes under budget.
        await asyncio.sleep(0.01)
        return end_response

    mock_provider = AsyncMock()
    mock_provider.chat = slow_chat

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=10, timeout_seconds=1.0,
    )
    ctx = SessionContext()
    result = await loop.run("hello", ctx)

    assert result == "done"

    # The injection must appear exactly once across ALL snapshots (the same
    # message shows up in every snapshot AFTER it was injected, so we check
    # the final snapshot, where the message should appear exactly once).
    final = captured_messages[-1]
    soft_hits = [
        m for m in final
        if m.role == "user" and m.content == _SOFT_DEADLINE_MSG
    ]
    assert len(soft_hits) == 1, (
        f"expected exactly one soft-deadline injection in the final snapshot, "
        f"got {len(soft_hits)}"
    )


async def test_timeout_appends_var_registry_summary():
    """TimeoutError must surface concrete variable names/shapes so the user can
    recover partial work, not just the opaque 'may be available' line."""
    async def slow_chat(messages, tools, **kwargs):
        await asyncio.sleep(10)
        return LLMResponse(stop_reason="end_turn", text="never")

    import pandas as pd

    mock_provider = AsyncMock()
    mock_provider.chat = slow_chat

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=10, timeout_seconds=0.05,
    )
    ctx = SessionContext()
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2]}))
    ctx.vars.set("df2", pd.DataFrame({"b": [3, 4, 5]}))

    result = await loop.run("hello", ctx)

    assert "timed out" in result.lower()
    assert "Partial results still in variable registry" in result
    assert "df1" in result
    assert "df2" in result
    # Shape should be in the summary too (2x1 / 3x1 in pandas)
    assert "2x1" in result
    assert "3x1" in result


async def test_timeout_override_is_honored():
    """timeout_override must replace the constructor default for a single run."""
    async def slow_chat(messages, tools, **kwargs):
        await asyncio.sleep(0.25)
        return LLMResponse(stop_reason="end_turn", text="done")

    mock_provider = AsyncMock()
    mock_provider.chat = slow_chat

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    # Constructor default of 0.05s would time the slow_chat out; the override
    # of 1.0s must let it finish.
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=10, timeout_seconds=0.05,
    )
    ctx = SessionContext()

    result = await loop.run("hello", ctx, timeout_override=1.0)
    assert result == "done"


async def test_run_without_override_still_uses_constructor_timeout():
    """Regression guard: omitting timeout_override must not broaden the budget."""
    async def slow_chat(messages, tools, **kwargs):
        await asyncio.sleep(10)
        return LLMResponse(stop_reason="end_turn", text="never")

    mock_provider = AsyncMock()
    mock_provider.chat = slow_chat

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(
        provider=mock_provider, tools=tools, hooks=hooks, permissions=perms,
        max_iterations=10, timeout_seconds=0.05,
    )
    ctx = SessionContext()

    result = await loop.run("hello", ctx)
    assert "timed out" in result.lower()
