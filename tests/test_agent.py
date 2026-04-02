# tests/test_agent.py
import pytest
from unittest.mock import AsyncMock
from pydantic import BaseModel
from yigthinker.types import Message, LLMResponse, ToolResult, ToolUse, HookResult
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
) -> tuple[AgentLoop, SessionContext]:
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=responses)

    tools = ToolRegistry()
    tools.register(EchoTool())

    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]} if allow_all else {})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
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
