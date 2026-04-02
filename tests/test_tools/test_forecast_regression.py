import pandas as pd
import numpy as np
import pytest
from yigthinker.tools.forecast.forecast_regression import ForecastRegressionTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_regression_data():
    ctx = SessionContext()
    np.random.seed(42)
    n = 50
    x1 = np.random.rand(n) * 100
    x2 = np.random.rand(n) * 50
    y = 2.5 * x1 + 1.2 * x2 + np.random.randn(n) * 5
    df = pd.DataFrame({"revenue": y, "ad_spend": x1, "headcount": x2})
    ctx.vars.set("factors", df)
    return ctx


async def test_regression_returns_coefficients(ctx_with_regression_data):
    tool = ForecastRegressionTool()
    input_obj = tool.input_schema(
        var_name="factors", target_col="revenue", feature_cols=["ad_spend", "headcount"]
    )
    result = await tool.execute(input_obj, ctx_with_regression_data)
    assert not result.is_error
    content = result.content
    assert "coefficients" in content
    assert "r_squared" in content
    assert content["r_squared"] > 0.9
