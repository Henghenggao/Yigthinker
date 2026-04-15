from __future__ import annotations
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ExploreOverviewInput(BaseModel):
    var_name: str = "last_query"


class ExploreOverviewTool:
    name = "explore_overview"
    description = (
        "Generate a comprehensive overview of a dataset: "
        "row/column counts, data types, missing value rates, numeric distributions, "
        "and categorical value frequencies."
    )
    input_schema = ExploreOverviewInput
    is_concurrency_safe = True

    async def execute(self, input: ExploreOverviewInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        numeric_cols = list(df.select_dtypes(include="number").columns)
        cat_cols = list(df.select_dtypes(include=["object", "category", "string"]).columns)

        numeric_summary = {
            col: {
                "mean": round(float(df[col].mean()), 4),
                "std": round(float(df[col].std()), 4),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "missing_pct": round(float(df[col].isna().mean()) * 100, 2),
            }
            for col in numeric_cols
        }

        cat_summary = {
            col: {
                "unique_values": int(df[col].nunique()),
                "top_values": df[col].value_counts().head(5).to_dict(),
                "missing_pct": round(float(df[col].isna().mean()) * 100, 2),
            }
            for col in cat_cols
        }

        return ToolResult(
            tool_use_id="",
            content={
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": list(df.columns),
                "numeric_summary": numeric_summary,
                "categorical_summary": cat_summary,
            },
        )
