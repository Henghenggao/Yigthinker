import pandas as pd
import pytest
from yigthinker.tools.forecast.forecast_evaluate import ForecastEvaluateTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_actuals_and_predictions():
    ctx = SessionContext()
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=6, freq="ME"),
        "actual": [100, 110, 105, 115, 120, 118],
        "predicted": [98, 112, 107, 113, 122, 116],
    })
    ctx.vars.set("eval_data", df)
    return ctx


async def test_evaluate_returns_metrics(ctx_with_actuals_and_predictions):
    tool = ForecastEvaluateTool()
    input_obj = tool.input_schema(
        var_name="eval_data", actual_col="actual", predicted_col="predicted"
    )
    result = await tool.execute(input_obj, ctx_with_actuals_and_predictions)
    assert not result.is_error
    content = result.content
    assert "mape" in content
    assert "rmse" in content
    assert "r_squared" in content
    assert content["mape"] < 5.0
