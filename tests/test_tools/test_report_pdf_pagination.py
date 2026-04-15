import re

import pandas as pd
import pytest

from yigthinker.tools.reports.report_generate import (
    ReportGenerateInput,
    ReportGenerateTool,
)
from yigthinker.session import SessionContext


@pytest.mark.asyncio
async def test_pdf_with_100_rows_does_not_error(tmp_path):
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    df = pd.DataFrame({"id": range(100), "value": range(100, 200)})
    ctx.vars.set("big", df)

    tool = ReportGenerateTool()
    inp = ReportGenerateInput(
        var_name="big",
        format="pdf",
        output_path=str(tmp_path / "big_report.pdf"),
        title="Big Report",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"PDF generation failed: {result.content}"

    out = tmp_path / "big_report.pdf"
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.asyncio
async def test_pdf_with_100_rows_paginates_to_multiple_pages(tmp_path):
    """With LongTable + repeatRows=1, a 100-row DataFrame should span multiple pages.

    Validation is qualitative: we count '/Type /Page' occurrences in the raw PDF
    bytes. This is not perfectly reliable (streams can be compressed) but for
    ReportLab's default uncompressed output it works. If the count isn't > 1,
    we fall back to asserting the file is non-trivially sized (smoke check).
    """
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    df = pd.DataFrame({"id": range(100), "value": range(100, 200)})
    ctx.vars.set("big", df)

    tool = ReportGenerateTool()
    inp = ReportGenerateInput(
        var_name="big",
        format="pdf",
        output_path=str(tmp_path / "big_report.pdf"),
        title="Big Report",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"PDF generation failed: {result.content}"

    content = (tmp_path / "big_report.pdf").read_bytes()
    # Count "/Type /Page" but not "/Type /Pages" (the catalog node).
    page_refs = re.findall(rb"/Type\s*/Page(?!s)", content)
    if page_refs:
        assert len(page_refs) > 1, (
            f"Expected multi-page PDF for 100-row DataFrame, got {len(page_refs)} page(s)"
        )
    else:
        # Compressed stream — fall back to smoke check.
        assert len(content) > 1000
