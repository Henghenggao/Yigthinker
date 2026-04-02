import pandas as pd
import json
import pytest
from yigthinker.tools.visualization.chart_create import ChartCreateTool
from yigthinker.tools.visualization.chart_modify import ChartModifyTool
from yigthinker.session import SessionContext


@pytest.fixture
async def ctx_with_chart():
    ctx = SessionContext()
    df = pd.DataFrame({"month": ["Jan", "Feb"], "rev": [100, 150]})
    ctx.vars.set("data", df)
    create_tool = ChartCreateTool()
    await create_tool.execute(
        create_tool.input_schema(var_name="data", chart_type="bar", x="month", y="rev"),
        ctx,
    )
    return ctx


async def test_modify_title(ctx_with_chart):
    tool = ChartModifyTool()
    input_obj = tool.input_schema(chart_name="last_chart", title="New Title")
    result = await tool.execute(input_obj, ctx_with_chart)
    assert not result.is_error
    chart_json = json.loads(ctx_with_chart.vars._vars["last_chart"])
    assert chart_json["layout"]["title"]["text"] == "New Title"


async def test_modify_missing_chart_returns_error():
    tool = ChartModifyTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(chart_name="nonexistent_chart", title="X")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
