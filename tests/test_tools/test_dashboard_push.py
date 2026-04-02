import json
import pandas as pd
from yigthinker.tools.visualization.chart_create import ChartCreateTool
from yigthinker.tools.visualization.dashboard_push import DashboardPushTool
from yigthinker.session import SessionContext


async def test_push_chart_returns_entry():
    ctx = SessionContext()
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    ctx.vars.set("data", df)

    create_tool = ChartCreateTool()
    await create_tool.execute(
        create_tool.input_schema(var_name="data", chart_type="line", x="x", y="y"),
        ctx,
    )

    push_tool = DashboardPushTool()
    input_obj = push_tool.input_schema(chart_name="last_chart", title="My Chart")
    result = await push_tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "dashboard_id" in result.content
    assert len(ctx.settings.get("_dashboard_queue", [])) == 1


async def test_push_missing_chart_returns_error():
    ctx = SessionContext()
    push_tool = DashboardPushTool()
    input_obj = push_tool.input_schema(chart_name="no_chart", title="X")
    result = await push_tool.execute(input_obj, ctx)
    assert result.is_error
