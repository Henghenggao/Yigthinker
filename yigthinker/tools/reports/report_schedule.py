from __future__ import annotations
import uuid
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


class ReportScheduleInput(BaseModel):
    report_name: str
    cron: str
    var_name: str
    format: str = "excel"
    output_path: str


class ReportScheduleTool:
    name = "report_schedule"
    description = (
        "Register a report for scheduled generation. "
        "(Status: LIMITED -- schedules are stored in memory only and do not persist. "
        "APScheduler integration is not yet available.)"
    )
    input_schema = ReportScheduleInput

    async def execute(self, input: ReportScheduleInput, ctx: SessionContext) -> ToolResult:
        schedule_id = str(uuid.uuid4())[:8]
        entry = {
            "schedule_id": schedule_id,
            "report_name": input.report_name,
            "cron": input.cron,
            "var_name": input.var_name,
            "format": input.format,
            "output_path": input.output_path,
        }
        if "_scheduled_reports" not in ctx.settings:
            ctx.settings["_scheduled_reports"] = []
        ctx.settings["_scheduled_reports"].append(entry)
        return ToolResult(
            tool_use_id="",
            content={"schedule_id": schedule_id, "cron": input.cron, "report_name": input.report_name},
        )
