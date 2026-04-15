import pandas as pd
from yigthinker.tools.visualization.chart_recommend import ChartRecommendTool
from yigthinker.session import SessionContext


async def test_recommends_line_for_time_series():
    ctx = SessionContext()
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=12, freq="ME"), "revenue": range(12)})
    ctx.vars.set("ts", df)
    tool = ChartRecommendTool()
    input_obj = tool.input_schema(var_name="ts")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    recommendations = result.content["recommendations"]
    types = [r["chart_type"] for r in recommendations]
    assert "line" in types


async def test_recommends_histogram_for_single_numeric():
    ctx = SessionContext()
    df = pd.DataFrame({"value": [1.2, 3.4, 2.1, 5.6, 4.3]})
    ctx.vars.set("nums", df)
    tool = ChartRecommendTool()
    input_obj = tool.input_schema(var_name="nums")
    result = await tool.execute(input_obj, ctx)
    types = [r["chart_type"] for r in result.content["recommendations"]]
    assert "histogram" in types
