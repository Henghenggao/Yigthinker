import pandas as pd
from yigthinker.tools.exploration.explore_drilldown import ExploreDrilldownTool
from yigthinker.session import SessionContext


async def test_drilldown_filters_by_dimension():
    ctx = SessionContext()
    df = pd.DataFrame({
        "region": ["N", "S", "N", "S", "N"],
        "revenue": [100, 200, 150, 250, 120],
    })
    ctx.vars.set("sales", df)
    tool = ExploreDrilldownTool()
    input_obj = tool.input_schema(
        var_name="sales", dimension="region", dimension_value="N", output_var="north"
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    north_df = ctx.vars.get("north")
    assert len(north_df) == 3
    assert all(north_df["region"] == "N")
