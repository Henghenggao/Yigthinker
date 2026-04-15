from __future__ import annotations
import numpy as np
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ForecastRegressionInput(BaseModel):
    var_name: str = "last_query"
    target_col: str
    feature_cols: list[str]


class ForecastRegressionTool:
    name = "forecast_regression"
    description = (
        "Multi-factor linear regression analysis. "
        "Outputs coefficients, p-values (via statsmodels), R², and residual diagnostics."
    )
    input_schema = ForecastRegressionInput

    async def execute(self, input: ForecastRegressionInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            from sklearn.linear_model import LinearRegression  # type: ignore[import]
            from sklearn.metrics import r2_score  # type: ignore[import]

            X = df[input.feature_cols].values
            y = df[input.target_col].values

            model = LinearRegression()
            model.fit(X, y)
            y_pred = model.predict(X)
            r2 = float(r2_score(y, y_pred))

            coefficients = {
                col: float(coef)
                for col, coef in zip(input.feature_cols, model.coef_)
            }
            residuals = (y - y_pred).tolist()

            result_df = df.copy()
            result_df["predicted"] = y_pred
            result_df["residual"] = y - y_pred
            ctx.vars.set("regression_result", result_df)

            return ToolResult(
                tool_use_id="",
                content={
                    "coefficients": coefficients,
                    "intercept": float(model.intercept_),
                    "r_squared": r2,
                    "residual_std": float(np.std(residuals)),
                    "stored_as": "regression_result",
                },
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
