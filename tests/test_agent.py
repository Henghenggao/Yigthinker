# tests/test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from yigthinker.types import Message, LLMResponse, StreamEvent, ToolResult, ToolUse, HookResult
from yigthinker.session import SessionContext
from yigthinker.permissions import PermissionSystem
from yigthinker.tools.registry import ToolRegistry
from yigthinker.hooks.registry import HookRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.agent import AgentLoop


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
