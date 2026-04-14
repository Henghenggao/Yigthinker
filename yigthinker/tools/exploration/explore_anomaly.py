from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ExploreAnomalyInput(BaseModel):
    var_name: str = "last_query"
    columns: list[str] | None = None
    method: str = "iqr"
    output_var: str = "anomalies"


class ExploreAnomalyTool:
    name = "explore_anomaly"
    description = (
        "Detect anomalies in a dataset using IQR or Z-score methods. "
        "Outputs flagged records with anomaly scores. "
        "Stored in output_var for further analysis."
    )
    input_schema = ExploreAnomalyInput
    is_concurrency_safe = True

    async def execute(self, input: ExploreAnomalyInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        cols = input.columns or list(df.select_dtypes(include="number").columns)
        if not cols:
            return ToolResult(tool_use_id="", content="No numeric columns found", is_error=True)

        anomaly_mask = pd.Series(False, index=df.index)
        anomaly_details: list[dict[str, Any]] = []

        for col in cols:
            series = df[col].astype(float)
            if input.method == "iqr":
                q1, q3 = series.quantile(0.25), series.quantile(0.75)
                iqr = q3 - q1
                mask = (series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)
            else:  # zscore
                z_scores = (series - series.mean()) / series.std()
                mask = z_scores.abs() > 3

            anomaly_mask |= mask
            if mask.any():
                anomaly_details.append({
                    "column": col,
                    "anomaly_count": int(mask.sum()),
                    "anomaly_rows": df[mask].index.tolist()[:10],
                })

        anomaly_df = df[anomaly_mask]
        ctx.vars.set(input.output_var, anomaly_df)

        return ToolResult(
            tool_use_id="",
            content={
                "method": input.method,
                "total_anomalies": int(anomaly_mask.sum()),
                "anomalies": anomaly_details,
                "stored_as": input.output_var,
            },
        )
