from __future__ import annotations
import json
from typing import Literal
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext

ChartType = Literal["bar", "line", "scatter", "pie", "histogram", "area", "heatmap"]

_CHART_BUILDERS: dict[str, type] = {
    "bar": px.bar,
    "line": px.line,
    "scatter": px.scatter,
    "pie": px.pie,
    "histogram": px.histogram,
    "area": px.area,
}


class ChartCreateInput(BaseModel):
    var_name: str = "last_query"
    chart_type: ChartType = "bar"
    x: str
    y: str | None = None
    color: str | None = None
    title: str = ""
    chart_name: str = "last_chart"


class ChartCreateTool:
    name = "chart_create"
    description = (
        "Generate a Plotly chart from a registered DataFrame. "
        "Supported types: bar, line, scatter, pie, histogram, area. "
        "Applies theme from settings. Stores chart JSON as chart_name in var registry."
    )
    input_schema = ChartCreateInput

    async def execute(self, input: ChartCreateInput, ctx: SessionContext) -> ToolResult:
        try:
            df = ctx.vars.get(input.var_name)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            builder = _CHART_BUILDERS.get(input.chart_type)
            if builder is None:
                return ToolResult(
                    tool_use_id="",
                    content=f"Unknown chart_type '{input.chart_type}'. Available: {list(_CHART_BUILDERS)}",
                    is_error=True,
                )

            kwargs: dict = {"data_frame": df, "x": input.x}
            if input.y:
                kwargs["y"] = input.y
            if input.color:
                kwargs["color"] = input.color
            if input.title:
                kwargs["title"] = input.title

            # Apply theme palette
            theme = ctx.settings.get("theme", {})
            palette = theme.get("palette")
            if palette:
                kwargs["color_discrete_sequence"] = palette

            fig = builder(**kwargs)
            chart_json = fig.to_json()

            # Store chart JSON in var registry (as a special dict, not DataFrame)
            ctx.vars._vars[input.chart_name] = chart_json  # type: ignore[attr-defined]

            return ToolResult(
                tool_use_id="",
                content={"chart_name": input.chart_name, "chart_json": chart_json},
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
