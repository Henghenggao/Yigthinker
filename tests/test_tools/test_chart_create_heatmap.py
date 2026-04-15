import pandas as pd
import pytest
from yigthinker.tools.visualization.chart_create import ChartCreateTool, ChartCreateInput
from yigthinker.session import SessionContext


async def test_heatmap_creates_chart():
    ctx = SessionContext()
    df = pd.DataFrame({
        "x": ["A", "A", "B", "B"],
        "y": ["P", "Q", "P", "Q"],
        "val": [1, 2, 3, 4],
    })
    ctx.vars.set("df1", df)

    tool = ChartCreateTool()
    inp = ChartCreateInput(
        var_name="df1", chart_type="heatmap", x="x", y="y", chart_name="hm"
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"Heatmap creation failed: {result.content}"
    assert "hm" in ctx.vars._vars


async def test_heatmap_ignores_palette():
    """Heatmaps should not fail when a theme palette is set (palette not applicable)."""
    ctx = SessionContext()
    ctx.settings["theme"] = {"palette": ["#ff0000", "#00ff00"]}
    df = pd.DataFrame({
        "x": ["A", "A", "B", "B"],
        "y": ["P", "Q", "P", "Q"],
        "val": [1, 2, 3, 4],
    })
    ctx.vars.set("df1", df)

    tool = ChartCreateTool()
    inp = ChartCreateInput(
        var_name="df1", chart_type="heatmap", x="x", y="y", chart_name="hm"
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"Heatmap creation failed: {result.content}"
