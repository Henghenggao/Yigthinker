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


def _build_heatmap(data_frame, x, y, **kwargs):
    """Build a heatmap using go.Heatmap from a long-form DataFrame.

    Pivots the DataFrame (index=y, columns=x) and aggregates numeric columns
    by mean. Discards color_discrete_sequence since it's not applicable to
    continuous heatmap colorscales.
    """
    kwargs.pop("color_discrete_sequence", None)  # not applicable to heatmaps
    kwargs.pop("color", None)  # color column is not used for heatmap z
    pivot = data_frame.pivot_table(index=y, columns=x, aggfunc="mean", observed=True)
    # pivot_table with no explicit values produces a MultiIndex [value_col, x_col].
    # Collapse to the first numeric value column so heatmap columns are x-axis categories.
    if hasattr(pivot.columns, "nlevels") and pivot.columns.nlevels > 1:
        first_value = pivot.columns.get_level_values(0)[0]
        pivot = pivot[first_value]
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values.tolist(),
        x=[str(c) for c in pivot.columns],
        y=[str(i) for i in pivot.index],
        colorscale="Blues",
    ))
    title = kwargs.get("title", "")
    if title:
        fig.update_layout(title=title)
    return fig


_CHART_BUILDERS: dict[str, type] = {
    "bar": px.bar,
    "line": px.line,
    "scatter": px.scatter,
    "pie": px.pie,
    "histogram": px.histogram,
    "area": px.area,
    "heatmap": _build_heatmap,
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
        "Supported types: bar, line, scatter, pie, histogram, area, heatmap. "
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

            # Store chart JSON in var registry with chart type tag
            ctx.vars.set(input.chart_name, chart_json, var_type="chart")

            return ToolResult(
                tool_use_id="",
                content={"chart_name": input.chart_name, "chart_json": chart_json},
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
