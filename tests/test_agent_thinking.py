from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from yigthinker.agent import AgentLoop
from yigthinker.types import LLMResponse, ToolUse, ToolResult
from yigthinker.tools.registry import ToolRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext


def make_ctx() -> SessionContext:
    return SessionContext(session_id="s1", transcript_path="")


async def test_thinking_blocks_included_in_tool_use_message():
    """When LLM returns thinking blocks with tool_use, they appear in the assistant content."""
    tool_use = ToolUse(id="tu1", name="echo", input={"msg": "hi"})
    thinking_block = {"type": "thinking", "thinking": "Let me call the tool"}

    registry = ToolRegistry()
    mock_tool = MagicMock()
    mock_tool.name = "echo"
    mock_tool.is_concurrency_safe = False

    class EchoInput(BaseModel):
        msg: str = ""

    mock_tool.input_schema = EchoInput
    mock_tool.execute = AsyncMock(return_value=ToolResult(tool_use_id="tu1", content="hi"))
    registry.register(mock_tool)

    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=[
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[tool_use],
            thinking_blocks=[thinking_block],
        ),
        LLMResponse(stop_reason="end_turn", text="Done"),
    ])

    loop = AgentLoop(
        provider=provider,
        tools=registry,
        hooks=HookExecutor(HookRegistry()),
        permissions=PermissionSystem({"allow": ["*"]}),
    )

    ctx = make_ctx()
    await loop.run("run echo", ctx)

    # Find the assistant message that has tool_use blocks
    assistant_msgs = [m for m in ctx.messages if m.role == "assistant" and isinstance(m.content, list)]
    assert len(assistant_msgs) >= 1
    content = assistant_msgs[0].content
    types_in_content = [b.get("type") for b in content if isinstance(b, dict)]
    assert "thinking" in types_in_content
