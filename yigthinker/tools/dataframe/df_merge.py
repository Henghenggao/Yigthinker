from __future__ import annotations
from typing import Literal
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class DfMergeInput(BaseModel):
    left_var: str
    right_var: str
    output_var: str = "df_merged"
    on: str | list[str] | None = None
    how: Literal["inner", "outer", "left", "right"] = "inner"


class DfMergeTool:
    name = "df_merge"
    description = (
        "Merge (join) two registered DataFrames. "
        "Supports inner/outer/left/right joins. "
        "If 'on' is omitted, common column names are used as join keys automatically."
    )
    input_schema = DfMergeInput

    async def execute(self, input: DfMergeInput, ctx: SessionContext) -> ToolResult:
        try:
            left = ctx.vars.get(input.left_var)
            right = ctx.vars.get(input.right_var)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            join_keys = input.on
            if join_keys is None:
                common = list(set(left.columns) & set(right.columns))
                if not common:
                    return ToolResult(
                        tool_use_id="",
                        content=f"No common columns between '{input.left_var}' and '{input.right_var}'. Specify 'on' explicitly.",
                        is_error=True,
                    )
                join_keys = common

            merged = pd.merge(left, right, on=join_keys, how=input.how)
            ctx.vars.set(input.output_var, merged)

            cm = ctx.context_manager
            return ToolResult(
                tool_use_id="",
                content={
                    "stored_as": input.output_var,
                    "join_keys": join_keys,
                    "how": input.how,
                    "preview": cm.summarize_dataframe_result(merged),
                },
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
