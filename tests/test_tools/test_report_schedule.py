from yigthinker.tools.reports.report_schedule import ReportScheduleTool
from yigthinker.session import SessionContext


async def test_schedule_creates_entry():
    tool = ReportScheduleTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(
        report_name="monthly_pl",
        cron="0 8 1 * *",
        var_name="pl_data",
        format="excel",
        output_path="/reports/monthly_pl.xlsx",
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "schedule_id" in result.content
    schedules = ctx.settings.get("_scheduled_reports", [])
    assert len(schedules) == 1
    assert schedules[0]["cron"] == "0 8 1 * *"
