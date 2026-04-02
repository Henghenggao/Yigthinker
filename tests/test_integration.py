# tests/test_integration.py
"""End-to-end test: user query → agent loop → tool execution → response."""
import pytest
from unittest.mock import AsyncMock
from pydantic import BaseModel
from yigthinker.types import Message, LLMResponse, ToolResult, ToolUse
from yigthinker.session import SessionContext
from yigthinker.permissions import PermissionSystem
from yigthinker.tools.registry import ToolRegistry
from yigthinker.hooks.registry import HookRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.agent import AgentLoop
from yigthinker.context_manager import ContextManager
import pandas as pd


class SumInput(BaseModel):
    numbers: list[float]


class SumTool:
    """Adds numbers and stores result in VarRegistry as a DataFrame."""
    name = "sum_numbers"
    description = "Sum a list of numbers"
    input_schema = SumInput

    async def execute(self, input: SumInput, ctx: SessionContext) -> ToolResult:
        total = sum(input.numbers)
        df = pd.DataFrame({"result": [total]})
        ctx.vars.set("last_sum", df)
        return ToolResult(tool_use_id="", content=str(total))


@pytest.mark.asyncio
async def test_full_pipeline_with_var_registry():
    """
    Scenario: LLM asks to sum numbers, tool stores result in VarRegistry,
    LLM receives result and returns final answer.
    """
    # Two LLM turns: first requests tool, then gives final answer
    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="sum_numbers", input={"numbers": [1, 2, 3]})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="The sum is 6.0")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])

    tools = ToolRegistry()
    tools.register(SumTool())
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["sum_numbers"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    result = await loop.run("Sum 1, 2, and 3", ctx)

    assert result == "The sum is 6.0"
    # VarRegistry has the DataFrame side-effect
    assert "last_sum" in ctx.vars
    df = ctx.vars.get("last_sum")
    assert df["result"][0] == 6.0


@pytest.mark.asyncio
async def test_hook_audits_all_tool_calls():
    """PostToolUse hook fires for every tool call; audit log accumulates."""
    audit_log = []

    reg = HookRegistry()

    @reg.hook("PostToolUse", matcher="*")
    async def audit(event):
        from yigthinker.types import HookResult
        audit_log.append({"tool": event.tool_name, "input": event.tool_input})
        return HookResult.ALLOW

    tool_response = LLMResponse(
        stop_reason="tool_use",
        tool_uses=[ToolUse(id="tu1", name="sum_numbers", input={"numbers": [10, 20]})],
    )
    final_response = LLMResponse(stop_reason="end_turn", text="Done")

    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(side_effect=[tool_response, final_response])

    tools = ToolRegistry()
    tools.register(SumTool())
    hooks = HookExecutor(reg)
    perms = PermissionSystem({"allow": ["sum_numbers"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    ctx = SessionContext()

    await loop.run("Sum 10 and 20", ctx)

    assert len(audit_log) == 1
    assert audit_log[0]["tool"] == "sum_numbers"


@pytest.mark.asyncio
async def test_context_manager_summarizes_large_result():
    """ContextManager produces a summary dict for DataFrames > 10 rows."""
    cm = ContextManager()
    df = pd.DataFrame({"value": range(1000)})
    summary = cm.summarize_dataframe_result(df)
    assert summary["type"] == "dataframe_summary"
    assert summary["total_rows"] == 1000
    assert len(summary["sample"]) == 10
