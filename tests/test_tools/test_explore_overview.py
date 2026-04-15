import pandas as pd
from yigthinker.tools.exploration.explore_overview import ExploreOverviewTool
from yigthinker.session import SessionContext


async def test_overview_returns_key_metrics():
    ctx = SessionContext()
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=100, freq="D"),
        "revenue": [i * 10 for i in range(100)],
        "region": ["N"] * 50 + ["S"] * 50,
    })
    ctx.vars.set("data", df)
    tool = ExploreOverviewTool()
    input_obj = tool.input_schema(var_name="data")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    content = result.content
    assert "row_count" in content
    assert "column_count" in content
    assert "numeric_summary" in content
