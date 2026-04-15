import pandas as pd
from yigthinker.tools.exploration.explore_anomaly import ExploreAnomalyTool
from yigthinker.session import SessionContext


async def test_detects_outliers():
    ctx = SessionContext()
    values = [100.0] * 20 + [5000.0]  # one clear outlier
    df = pd.DataFrame({"revenue": values})
    ctx.vars.set("data", df)
    tool = ExploreAnomalyTool()
    input_obj = tool.input_schema(var_name="data", columns=["revenue"])
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    content = result.content
    assert "anomalies" in content
    assert len(content["anomalies"]) >= 1
