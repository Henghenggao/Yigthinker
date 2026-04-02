import pandas as pd
import pytest
from yigthinker.tools.forecast.forecast_timeseries import ForecastTimeseriesTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_timeseries():
    ctx = SessionContext()
    dates = pd.date_range("2023-01-01", periods=24, freq="ME")
    values = [100 + i * 5 + (i % 3) * 10 for i in range(24)]
    df = pd.DataFrame({"date": dates, "revenue": values})
    ctx.vars.set("monthly", df)
    return ctx


async def test_forecast_returns_predictions(ctx_with_timeseries):
    tool = ForecastTimeseriesTool()
    input_obj = tool.input_schema(
        var_name="monthly", date_col="date", value_col="revenue", periods=6
    )
    result = await tool.execute(input_obj, ctx_with_timeseries)
    assert not result.is_error
    assert "forecast" in ctx_with_timeseries.vars
    forecast_df = ctx_with_timeseries.vars.get("forecast")
    assert len(forecast_df) == 6
    assert "predicted" in forecast_df.columns


async def test_forecast_includes_confidence_intervals(ctx_with_timeseries):
    tool = ForecastTimeseriesTool()
    input_obj = tool.input_schema(
        var_name="monthly", date_col="date", value_col="revenue", periods=3
    )
    result = await tool.execute(input_obj, ctx_with_timeseries)
    forecast_df = ctx_with_timeseries.vars.get("forecast")
    assert "lower_ci" in forecast_df.columns
    assert "upper_ci" in forecast_df.columns


async def test_missing_var_returns_error():
    tool = ForecastTimeseriesTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(var_name="nonexistent", date_col="date", value_col="val", periods=3)
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
