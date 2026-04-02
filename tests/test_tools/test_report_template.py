from pathlib import Path
import pytest
from yigthinker.tools.reports.report_template import ReportTemplateTool
from yigthinker.session import SessionContext


async def test_list_templates_returns_list(tmp_path):
    tmpl_dir = tmp_path / "templates"
    tmpl_dir.mkdir()
    (tmpl_dir / "balance_sheet.xlsx.j2").write_text("{{title}}")
    (tmpl_dir / "income_statement.xlsx.j2").write_text("{{title}}")

    tool = ReportTemplateTool(templates_dir=tmpl_dir)
    ctx = SessionContext()
    input_obj = tool.input_schema(action="list")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    templates = result.content["templates"]
    assert len(templates) == 2
    names = [t["name"] for t in templates]
    assert "balance_sheet" in names
