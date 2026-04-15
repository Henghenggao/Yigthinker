from __future__ import annotations
import numpy as np
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ForecastEvaluateInput(BaseModel):
    var_name: str = "last_query"
    actual_col: str = "actual"
    predicted_col: str = "predicted"


class ForecastEvaluateTool:
    name = "forecast_evaluate"
    description = (
        "Evaluate forecast accuracy: MAPE, RMSE, R², residual diagnostics. "
        "Compares predicted vs actual columns in a registered DataFrame."
    )
    input_schema = ForecastEvaluateInput
    is_concurrency_safe = True

    async def execute(self, input: ForecastEvaluateInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            from sklearn.metrics import mean_squared_error, r2_score  # type: ignore[import]

            actual = df[input.actual_col].astype(float).values
            predicted = df[input.predicted_col].astype(float).values

            mape = float(np.mean(np.abs((actual - predicted) / np.where(actual == 0, 1, actual))) * 100)
            rmse = float(np.sqrt(mean_squared_error(actual, predicted)))
            r2 = float(r2_score(actual, predicted))
            residuals = actual - predicted

            return ToolResult(
                tool_use_id="",
                content={
                    "mape": round(mape, 4),
                    "rmse": round(rmse, 4),
                    "r_squared": round(r2, 4),
                    "residual_mean": round(float(np.mean(residuals)), 4),
                    "residual_std": round(float(np.std(residuals)), 4),
                    "n_samples": len(actual),
                },
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
