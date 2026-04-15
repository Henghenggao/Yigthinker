"""Tests for waterfall chart type (Task 17)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.visualization.chart_create import (
    ChartCreateInput,
    ChartCreateTool,
)


@pytest.mark.asyncio
async def test_waterfall_creates_chart():
    ctx = SessionContext()
    df = pd.DataFrame({
        "category": ["Revenue", "COGS", "Gross Profit", "OpEx", "Net Income"],
        "amount": [500, -200, 300, -150, 150],
    })
    ctx.vars.set("pnl", df)

    tool = ChartCreateTool()
    inp = ChartCreateInput(
        var_name="pnl",
        chart_type="waterfall",
        x="category",
        y="amount",
        chart_name="wf",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"Waterfall creation failed: {result.content}"
    assert "wf" in ctx.vars
    # Verify generated chart JSON contains a waterfall trace
    chart_json = result.content["chart_json"]
    parsed = json.loads(chart_json)
    assert any(t.get("type") == "waterfall" for t in parsed.get("data", []))


@pytest.mark.asyncio
async def test_waterfall_applies_title():
    ctx = SessionContext()
    df = pd.DataFrame({"cat": ["a", "b"], "val": [1, -1]})
    ctx.vars.set("d", df)
    tool = ChartCreateTool()
    inp = ChartCreateInput(
        var_name="d",
        chart_type="waterfall",
        x="cat",
        y="val",
        title="P&L Bridge",
        chart_name="t",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    parsed = json.loads(result.content["chart_json"])
    assert parsed["layout"]["title"]["text"] == "P&L Bridge"
