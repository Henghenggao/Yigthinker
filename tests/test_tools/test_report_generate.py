import pandas as pd
import pytest
from pathlib import Path
from yigthinker.tools.reports.report_generate import ReportGenerateTool
from yigthinker.session import SessionContext


def _make_ctx(tmp_path):
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    df = pd.DataFrame({
        "account": ["Revenue", "COGS", "Gross Profit"],
        "amount": [1_000_000, 600_000, 400_000],
    })
    ctx.vars.set("pl_data", df)
    return ctx


async def test_generate_excel_report(tmp_path):
    tool = ReportGenerateTool()
    ctx = _make_ctx(tmp_path)
    output_path = str(tmp_path / "report.xlsx")
    input_obj = tool.input_schema(
        var_name="pl_data",
        format="excel",
        output_path=output_path,
        title="P&L Summary",
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, result.content
    assert Path(output_path).exists()
    assert Path(output_path).stat().st_size > 0


async def test_generate_with_missing_var_returns_error(tmp_path):
    tool = ReportGenerateTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        var_name="nonexistent", format="excel", output_path=str(tmp_path / "out.xlsx")
    )
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
