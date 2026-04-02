from __future__ import annotations
from typing import Any
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ChartRecommendInput(BaseModel):
    var_name: str = "last_query"


class ChartRecommendTool:
    name = "chart_recommend"
    description = (
        "Analyze a DataFrame's structure and recommend appropriate chart types. "
        "Time series -> line, proportion -> pie, distribution -> histogram, "
        "comparison -> bar, correlation -> scatter."
    )
    input_schema = ChartRecommendInput

    async def execute(self, input: ChartRecommendInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        recommendations: list[dict[str, Any]] = []
        numeric_cols = list(df.select_dtypes(include="number").columns)
        datetime_cols = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
        categorical_cols = list(df.select_dtypes(include=["object", "category", "string"]).columns)

        if datetime_cols and numeric_cols:
            recommendations.append({
                "chart_type": "line",
                "reason": "DateTime column detected — time series trend visualization",
                "x": datetime_cols[0],
                "y": numeric_cols[0],
            })

        if len(numeric_cols) == 1:
            recommendations.append({
                "chart_type": "histogram",
                "reason": "Single numeric column — distribution visualization",
                "x": numeric_cols[0],
            })

        if categorical_cols and numeric_cols:
            recommendations.append({
                "chart_type": "bar",
                "reason": "Categorical + numeric columns — comparison across categories",
                "x": categorical_cols[0],
                "y": numeric_cols[0],
            })

        if len(numeric_cols) >= 2:
            recommendations.append({
                "chart_type": "scatter",
                "reason": "Multiple numeric columns — correlation analysis",
                "x": numeric_cols[0],
                "y": numeric_cols[1],
            })

        if not recommendations:
            recommendations.append({
                "chart_type": "bar",
                "reason": "Default recommendation",
            })

        return ToolResult(
            tool_use_id="",
            content={"var_name": input.var_name, "recommendations": recommendations},
        )
