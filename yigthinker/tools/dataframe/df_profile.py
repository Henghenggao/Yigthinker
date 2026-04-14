from __future__ import annotations
from typing import Any
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class DfProfileInput(BaseModel):
    var_name: str = "df1"


class DfProfileTool:
    name = "df_profile"
    description = (
        "Generate a data quality profile for a registered DataFrame: "
        "missing values, type distribution, statistical summary, outlier detection."
    )
    input_schema = DfProfileInput
    is_concurrency_safe = True

    async def execute(self, input: DfProfileInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        total_rows = len(df)
        profile: dict[str, Any] = {
            "shape": {"rows": total_rows, "columns": len(df.columns)},
            "missing": {
                col: {"count": int(df[col].isna().sum()), "pct": round(df[col].isna().mean() * 100, 2)}
                for col in df.columns
            },
            "types": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "stats": df.describe(include="all").to_dict(),
        }

        outliers: dict[str, int] = {}
        for col in df.select_dtypes(include="number").columns:
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            n_outliers = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
            if n_outliers > 0:
                outliers[col] = n_outliers

        if outliers:
            profile["outliers"] = outliers

        return ToolResult(tool_use_id="", content=profile)
