from __future__ import annotations
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ExploreDrilldownInput(BaseModel):
    var_name: str = "last_query"
    dimension: str
    dimension_value: str
    output_var: str = "drilldown"
    group_by: str | None = None


class ExploreDrilldownTool:
    name = "explore_drilldown"
    description = (
        "Drill down into a specific dimension value (e.g., by region='North'). "
        "Outputs filtered/grouped data and stores result in output_var."
    )
    input_schema = ExploreDrilldownInput

    async def execute(self, input: ExploreDrilldownInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            filtered = df[df[input.dimension] == input.dimension_value]
            if input.group_by and input.group_by in filtered.columns:
                filtered = filtered.groupby(input.group_by).sum(numeric_only=True).reset_index()

            ctx.vars.set(input.output_var, filtered)
            cm = ctx.context_manager
            return ToolResult(
                tool_use_id="",
                content={
                    "dimension": input.dimension,
                    "value": input.dimension_value,
                    "row_count": len(filtered),
                    "stored_as": input.output_var,
                    "preview": cm.summarize_dataframe_result(filtered),
                },
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
