import pandas as pd
import pytest
from yigthinker.tools.visualization.chart_create import ChartCreateTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_sales():
    ctx = SessionContext()
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar", "Apr"],
        "revenue": [100, 150, 120, 200],
        "region": ["N", "N", "S", "S"],
    })
    ctx.vars.set("sales", df)
    return ctx


async def test_bar_chart_created(ctx_with_sales):
    tool = ChartCreateTool()
    input_obj = tool.input_schema(
        var_name="sales", chart_type="bar", x="month", y="revenue", title="Monthly Revenue"
    )
    result = await tool.execute(input_obj, ctx_with_sales)
    assert not result.is_error
    content = result.content
    assert "chart_json" in content
    assert "last_chart" in ctx_with_sales.vars._vars


async def test_line_chart_created(ctx_with_sales):
    tool = ChartCreateTool()
    input_obj = tool.input_schema(
        var_name="sales", chart_type="line", x="month", y="revenue"
    )
    result = await tool.execute(input_obj, ctx_with_sales)
    assert not result.is_error


async def test_missing_var_returns_error():
    tool = ChartCreateTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(var_name="nonexistent", chart_type="bar", x="a", y="b")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error


async def test_chart_respects_theme(ctx_with_sales):
    ctx_with_sales.settings["theme"] = {"palette": ["#ff0000", "#00ff00"]}
    tool = ChartCreateTool()
    input_obj = tool.input_schema(var_name="sales", chart_type="bar", x="month", y="revenue")
    result = await tool.execute(input_obj, ctx_with_sales)
    assert not result.is_error
