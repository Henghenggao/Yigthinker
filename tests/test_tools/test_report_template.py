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


async def test_preview_template_returns_content(tmp_path):
    tmpl_dir = tmp_path / "templates"
    tmpl_dir.mkdir()
    (tmpl_dir / "balance_sheet.xlsx.j2").write_text("{{title}}", encoding="utf-8")

    tool = ReportTemplateTool(templates_dir=tmpl_dir)
    ctx = SessionContext()
    input_obj = tool.input_schema(action="preview", name="balance_sheet")
    result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert result.content["content"] == "{{title}}"


async def test_preview_rejects_path_traversal_name(tmp_path):
    tmpl_dir = tmp_path / "templates"
    tmpl_dir.mkdir()
    (tmpl_dir / "balance_sheet.xlsx.j2").write_text("{{title}}", encoding="utf-8")
    (tmp_path / "leak.py").write_text("LEAK=1", encoding="utf-8")

    tool = ReportTemplateTool(templates_dir=tmpl_dir)
    ctx = SessionContext()
    input_obj = tool.input_schema(action="preview", name="../leak.py")
    result = await tool.execute(input_obj, ctx)

    assert result.is_error
    assert "Invalid template name" in str(result.content)
