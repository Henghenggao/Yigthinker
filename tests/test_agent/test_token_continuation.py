"""Max-tokens auto-continuation — up to 3 recovery attempts.

Production code: yigthinker/agent.py (handles `stop_reason == "max_tokens"`
with a continuation prompt, capped at 3 attempts).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from pydantic import BaseModel

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import LLMResponse, ToolResult


class EchoInput(BaseModel):
    message: str


class EchoTool:
    name = "echo"
    description = "Echoes the message"
    input_schema = EchoInput

    async def execute(self, input: EchoInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"echo: {input.message}")


async def test_max_tokens_recovery():
    """Agent auto-recovers from max_tokens by injecting continuation prompt."""
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[
        LLMResponse(stop_reason="max_tokens", text="partial...", tool_uses=[]),
        LLMResponse(stop_reason="end_turn", text="completed"),
    ])

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("do it", ctx)
    assert result == "completed"

    second_call_messages = mock_provider.chat.await_args_list[1].args[0]
    recovery_msgs = [m for m in second_call_messages if m.role == "user" and "token limit reached" in str(m.content)]
    assert len(recovery_msgs) == 1


async def test_max_tokens_recovery_cap_at_3():
    """max_tokens recovery is capped at 3 attempts; 4th max_tokens is treated as end."""
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[
        LLMResponse(stop_reason="max_tokens", text="p1", tool_uses=[]),
        LLMResponse(stop_reason="max_tokens", text="p2", tool_uses=[]),
        LLMResponse(stop_reason="max_tokens", text="p3", tool_uses=[]),
        LLMResponse(stop_reason="max_tokens", text="p4", tool_uses=[]),
        LLMResponse(stop_reason="max_tokens", text="p5", tool_uses=[]),
    ])

    tools = ToolRegistry()
    tools.register(EchoTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["echo"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("do it", ctx)
    assert result == "p4"
    assert mock_provider.chat.await_count == 4
