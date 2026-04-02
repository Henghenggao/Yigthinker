from __future__ import annotations
import json
import plotly.graph_objects as go
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ChartModifyInput(BaseModel):
    chart_name: str = "last_chart"
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    chart_type: str | None = None
    color_sequence: list[str] | None = None


class ChartModifyTool:
    name = "chart_modify"
    description = (
        "Modify an existing chart's style, title, axis labels, or chart type. "
        "Operates on a named chart stored in the var registry (default: 'last_chart'). "
        "Supports natural language descriptions via the LLM mapping them to these fields."
    )
    input_schema = ChartModifyInput

    async def execute(self, input: ChartModifyInput, ctx: SessionContext) -> ToolResult:
        chart_json = ctx.vars._vars.get(input.chart_name)  # type: ignore[attr-defined]
        if chart_json is None:
            return ToolResult(
                tool_use_id="",
                content=f"Chart '{input.chart_name}' not found. Create it first with chart_create.",
                is_error=True,
            )

        try:
            fig = go.Figure(json.loads(chart_json))

            if input.title is not None:
                fig.update_layout(title_text=input.title)
            if input.x_label is not None:
                fig.update_xaxes(title_text=input.x_label)
            if input.y_label is not None:
                fig.update_yaxes(title_text=input.y_label)
            if input.color_sequence is not None:
                for i, trace in enumerate(fig.data):
                    trace.update(marker_color=input.color_sequence[i % len(input.color_sequence)])

            updated_json = fig.to_json()
            ctx.vars._vars[input.chart_name] = updated_json  # type: ignore[attr-defined]
            return ToolResult(
                tool_use_id="",
                content={"chart_name": input.chart_name, "chart_json": updated_json},
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
