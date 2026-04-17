"""ArgPatch reflexion — on tool error, model emits a patch, agent retries once."""
from __future__ import annotations

from unittest.mock import AsyncMock

from pydantic import BaseModel

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import LLMResponse, ToolResult, ToolUse


class _DivideInput(BaseModel):
    numerator: int
    denominator: int


class _DivideTool:
    name = "divide"
    description = "Divide two integers. Errors on denominator=0."
    input_schema = _DivideInput

    def __init__(self) -> None:
        self.calls: list[_DivideInput] = []

    async def execute(self, input: _DivideInput, ctx: SessionContext) -> ToolResult:
        self.calls.append(input)
        if input.denominator == 0:
            return ToolResult(tool_use_id="", content="division by zero", is_error=True)
        return ToolResult(tool_use_id="", content=str(input.numerator / input.denominator))


async def test_reflexion_disabled_by_default_passes_error_through():
    """reflexion_enabled defaults False — tool error goes straight to LLM, no retry."""
    tool = _DivideTool()
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=[
        LLMResponse(
            stop_reason="tool_use", text="",
            tool_uses=[ToolUse(id="u1", name="divide", input={"numerator": 10, "denominator": 0})],
        ),
        LLMResponse(stop_reason="end_turn", text="can't divide by zero"),
    ])
    tools = ToolRegistry(); tools.register(tool)
    loop = AgentLoop(provider=mock, tools=tools, hooks=HookExecutor(HookRegistry()),
                     permissions=PermissionSystem({"allow": ["*"]}))
    # default: loop._reflexion_enabled is False
    await loop.run("compute", SessionContext())
    assert len(tool.calls) == 1  # exactly one call, no retry


async def test_reflexion_enabled_retries_once_with_patch():
    """reflexion_enabled=True — agent asks for patch, applies it, retries."""
    tool = _DivideTool()
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=[
        # Turn 1: tool call that fails
        LLMResponse(
            stop_reason="tool_use", text="",
            tool_uses=[ToolUse(id="u1", name="divide", input={"numerator": 10, "denominator": 0})],
        ),
        # Reflexion call: LLM emits a patch JSON
        LLMResponse(
            stop_reason="end_turn",
            text='{"tool_use_id": "u1", "patch": {"denominator": 2}}',
        ),
        # After patched retry succeeds, normal end_turn
        LLMResponse(stop_reason="end_turn", text="answer: 5"),
    ])
    tools = ToolRegistry(); tools.register(tool)
    loop = AgentLoop(provider=mock, tools=tools, hooks=HookExecutor(HookRegistry()),
                     permissions=PermissionSystem({"allow": ["*"]}))
    loop._reflexion_enabled = True  # type: ignore[attr-defined]

    result = await loop.run("compute", SessionContext())
    assert len(tool.calls) == 2
    assert tool.calls[0].denominator == 0
    assert tool.calls[1].denominator == 2
    assert "5" in result


async def test_reflexion_max_one_retry_per_tool_call():
    """Even with reflexion enabled, we only retry once per tool call."""
    tool = _DivideTool()
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=[
        LLMResponse(
            stop_reason="tool_use", text="",
            tool_uses=[ToolUse(id="u1", name="divide", input={"numerator": 10, "denominator": 0})],
        ),
        LLMResponse(stop_reason="end_turn",
                    text='{"tool_use_id": "u1", "patch": {"denominator": 0}}'),
        LLMResponse(stop_reason="end_turn", text="gave up"),
    ])
    tools = ToolRegistry(); tools.register(tool)
    loop = AgentLoop(provider=mock, tools=tools, hooks=HookExecutor(HookRegistry()),
                     permissions=PermissionSystem({"allow": ["*"]}))
    loop._reflexion_enabled = True  # type: ignore[attr-defined]

    await loop.run("compute", SessionContext())
    assert len(tool.calls) == 2  # original + one retry, no more


async def test_reflexion_aborts_when_llm_returns_tool_use():
    """If the reflexion LLM call returns tool_use (empty text), JSON parse fails
    and reflexion silently aborts — the original error flows through and no
    extra tool call is dispatched against the registry.

    Protects the abort path even if a future provider ignores the fact that we
    pass no tool schemas to the reflexion chat.
    """
    tool = _DivideTool()
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=[
        # Turn 1: tool call that fails
        LLMResponse(
            stop_reason="tool_use", text="",
            tool_uses=[ToolUse(id="u1", name="divide", input={"numerator": 10, "denominator": 0})],
        ),
        # Reflexion call: LLM emits tool_use instead of JSON — response.text is ""
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(id="u2", name="divide", input={"numerator": 1, "denominator": 1})],
        ),
        # After reflexion aborts, original error flows to LLM, which ends turn
        LLMResponse(stop_reason="end_turn", text="done"),
    ])
    tools = ToolRegistry(); tools.register(tool)
    loop = AgentLoop(provider=mock, tools=tools, hooks=HookExecutor(HookRegistry()),
                     permissions=PermissionSystem({"allow": ["*"]}))
    loop._reflexion_enabled = True  # type: ignore[attr-defined]

    result = await loop.run("compute", SessionContext())
    # Only the original call — reflexion aborted (empty text failed JSON parse),
    # and the tool_use from the reflexion response was never dispatched because
    # reflexion only consumes `response.text`, not `response.tool_uses`.
    assert len(tool.calls) == 1
    assert "done" in result
