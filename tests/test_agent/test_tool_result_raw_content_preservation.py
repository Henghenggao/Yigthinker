"""Tool truncation must preserve the raw content object for downstream adapters.

2026-04-18 UAT finding: a chart_create producing a Plotly JSON of ~8400 chars
(even a trivial 3-bar chart) tripped the MAX_RESULT_CHARS=8000 guard in
agent.py. The guard replaced ``result.content`` — a dict of
``{chart_name, chart_json}`` — with a truncated *string*. By the time the
on_tool_event callback fired, ``content_obj`` was a str, so
``structured_artifact_from_tool_result`` returned None and the chart
artifact was never surfaced to Teams.

Fix contract: ``content_obj`` in the tool_event payload must always be the
*original, untruncated* tool return value. Truncation is strictly a
rendering concern for the LLM message history (``content`` field); it
MUST NOT corrupt the structured payload consumed by channel adapters.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from yigthinker.agent import AgentLoop, MAX_RESULT_CHARS
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import Message, ToolResult


class _BigDictInput(BaseModel):
    pass


class _BigDictTool:
    """A tool that returns a dict whose serialized form exceeds MAX_RESULT_CHARS."""
    name = "big_dict_tool"
    description = "returns a big dict to force truncation path"
    input_schema = _BigDictInput
    is_concurrency_safe = True

    async def execute(self, input: _BigDictInput, ctx: SessionContext) -> ToolResult:
        # Build a dict whose serialized size comfortably exceeds 8000 chars.
        # We mirror the chart_create shape so the regression is expressive.
        big_payload = "x" * (MAX_RESULT_CHARS + 500)
        return ToolResult(
            tool_use_id="",
            content={"kind_hint": "chart", "chart_name": "sales", "chart_json": big_payload},
        )


def _make_loop() -> AgentLoop:
    """Minimal AgentLoop wiring for unit-testing _execute_tool in isolation."""
    provider = MagicMock()
    tools = ToolRegistry()
    tools.register(_BigDictTool())
    hooks = MagicMock()
    # Both PreToolUse and PostToolUse must return HookAggregateResult.ALLOW shape
    from yigthinker.types import HookAction, HookAggregateResult
    hooks.run = AsyncMock(return_value=HookAggregateResult(action=HookAction.ALLOW))
    permissions = MagicMock()
    permissions.check = MagicMock(return_value="allow")
    return AgentLoop(
        provider=provider,
        tools=tools,
        hooks=hooks,
        permissions=permissions,
    )


async def test_content_obj_stays_dict_when_content_gets_truncated():
    """Regression for 2026-04-18 chart-disappears-in-Teams bug.

    When a tool returns a dict whose serialized form > MAX_RESULT_CHARS,
    the LLM-facing `content` string may be truncated, but the `content_obj`
    passed to on_tool_event MUST remain the original dict so adapters can
    still extract structured artifacts (charts, tables, files)."""
    loop = _make_loop()
    ctx = SessionContext()

    captured: list[dict] = []

    def on_event(event_type: str, data: dict) -> None:
        if event_type == "tool_result":
            captured.append(data)

    # _execute_tool is the private path that carries the truncation logic.
    await loop._execute_tool(
        tool_name="big_dict_tool",
        tool_input={},
        tool_use_id="u1",
        ctx=ctx,
        on_tool_event=on_event,
    )

    assert len(captured) == 1
    event = captured[0]
    # The LLM-facing serialized string was truncated — confirm the pathway
    # triggered so we're actually exercising the regression:
    assert isinstance(event["content"], str)
    assert len(event["content"]) <= MAX_RESULT_CHARS + 200  # truncation marker adds <200 chars
    # The CRITICAL invariant: content_obj is the ORIGINAL dict, NOT the
    # truncated string. Adapter code relies on this.
    assert isinstance(event["content_obj"], dict)
    assert event["content_obj"]["chart_name"] == "sales"
    assert event["content_obj"]["chart_json"].startswith("xxx")
    assert len(event["content_obj"]["chart_json"]) > MAX_RESULT_CHARS


async def test_content_obj_unchanged_when_content_below_limit():
    """Baseline: short-return tools behave exactly as before — content_obj
    IS the content. This test guards against over-correction."""
    loop = _make_loop()
    ctx = SessionContext()

    class _SmallInput(BaseModel):
        pass

    class _SmallTool:
        name = "small_tool"
        description = "tiny return"
        input_schema = _SmallInput
        is_concurrency_safe = True

        async def execute(self, _: _SmallInput, __: SessionContext) -> ToolResult:
            return ToolResult(tool_use_id="", content={"ok": True})

    loop._tools.register(_SmallTool())

    captured: list[dict] = []
    def on_event(e, d):
        if e == "tool_result":
            captured.append(d)

    await loop._execute_tool(
        tool_name="small_tool",
        tool_input={},
        tool_use_id="u2",
        ctx=ctx,
        on_tool_event=on_event,
    )

    assert len(captured) == 1
    assert captured[0]["content_obj"] == {"ok": True}
