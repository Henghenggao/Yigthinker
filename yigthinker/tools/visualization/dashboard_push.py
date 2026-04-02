from __future__ import annotations
import uuid
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class DashboardPushInput(BaseModel):
    chart_name: str = "last_chart"
    title: str = ""
    description: str = ""


class DashboardPushTool:
    name = "dashboard_push"
    description = (
        "Push a chart to the Web Dashboard as a persistent entry. "
        "The dashboard is updated in real time via WebSocket (Phase 4). "
        "In CLI-only mode, records the push intent for later replay."
    )
    input_schema = DashboardPushInput

    async def execute(self, input: DashboardPushInput, ctx: SessionContext) -> ToolResult:
        chart_json = ctx.vars._vars.get(input.chart_name)  # type: ignore[attr-defined]
        if chart_json is None:
            return ToolResult(
                tool_use_id="",
                content=f"Chart '{input.chart_name}' not found. Create it with chart_create first.",
                is_error=True,
            )

        dashboard_id = str(uuid.uuid4())[:8]
        entry = {
            "dashboard_id": dashboard_id,
            "chart_name": input.chart_name,
            "title": input.title or input.chart_name,
            "description": input.description,
            "chart_json": chart_json,
        }

        if "_dashboard_queue" not in ctx.settings:
            ctx.settings["_dashboard_queue"] = []
        ctx.settings["_dashboard_queue"].append(entry)

        # Push to live dashboard (non-blocking, optional)
        server_url = ctx.settings.get("dashboard_url", "http://localhost:8765")
        try:
            from yigthinker.dashboard.websocket_client import DashboardClient
            import asyncio
            client = DashboardClient(server_url=server_url)
            asyncio.create_task(client.push(
                dashboard_id=dashboard_id,
                title=entry["title"],
                chart_json=chart_json,
            ))
        except Exception:
            pass  # Dashboard is optional

        return ToolResult(
            tool_use_id="",
            content={"dashboard_id": dashboard_id, "title": entry["title"]},
        )
