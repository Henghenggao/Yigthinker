from __future__ import annotations
import numpy as np
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ForecastTimeseriesInput(BaseModel):
    var_name: str = "last_query"
    date_col: str
    value_col: str
    periods: int = 12
    method: str = "auto"   # "auto" | "prophet" | "exponential_smoothing"


class ForecastTimeseriesTool:
    name = "forecast_timeseries"
    description = (
        "Time series forecasting using statsmodels Exponential Smoothing (default) "
        "or Prophet (if installed). "
        "Outputs predictions with confidence intervals. "
        "Results stored as 'forecast' DataFrame in the variable registry."
    )
    input_schema = ForecastTimeseriesInput

    async def execute(self, input: ForecastTimeseriesInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            series = df.set_index(input.date_col)[input.value_col].astype(float)

            # Try Prophet first if available and method permits
            if input.method in ("auto", "prophet"):
                try:
                    return await self._prophet_forecast(df, input, ctx, series)
                except ImportError:
                    pass  # Fall through to statsmodels

            return await self._statsmodels_forecast(series, input, ctx)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

    async def _prophet_forecast(self, df, input, ctx, series):
        from prophet import Prophet  # type: ignore[import]
        prophet_df = df[[input.date_col, input.value_col]].rename(
            columns={input.date_col: "ds", input.value_col: "y"}
        )
        model = Prophet(interval_width=0.95)
        model.fit(prophet_df)
        future = model.make_future_dataframe(periods=input.periods, freq="ME")
        forecast = model.predict(future).tail(input.periods)
        result_df = pd.DataFrame({
            "date": forecast["ds"].values,
            "predicted": forecast["yhat"].values,
            "lower_ci": forecast["yhat_lower"].values,
            "upper_ci": forecast["yhat_upper"].values,
        })
        ctx.vars.set("forecast", result_df)
        return ToolResult(
            tool_use_id="",
            content={"method": "prophet", "periods": input.periods, "sample": result_df.head(3).to_dict(orient="records")},
        )

    async def _statsmodels_forecast(self, series, input, ctx):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        model = ExponentialSmoothing(series, trend="add", seasonal=None, initialization_method="estimated")
        fit = model.fit(optimized=True)
        forecast_values = fit.forecast(input.periods)

        # Confidence interval approximation: ±1.96 * residual std
        residual_std = float(np.std(fit.resid))
        margin = 1.96 * residual_std

        # Determine frequency, fall back to "ME" if infer_freq returns None
        inferred_freq = pd.infer_freq(series.index)
        freq = inferred_freq if inferred_freq is not None else "ME"

        result_df = pd.DataFrame({
            "date": pd.date_range(series.index[-1], periods=input.periods + 1, freq=freq)[1:],
            "predicted": forecast_values.values,
            "lower_ci": forecast_values.values - margin,
            "upper_ci": forecast_values.values + margin,
        })
        ctx.vars.set("forecast", result_df)
        return ToolResult(
            tool_use_id="",
            content={"method": "exponential_smoothing", "periods": input.periods, "sample": result_df.head(3).to_dict(orient="records")},
        )
