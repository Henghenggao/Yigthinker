"""excel_write embed_chart: one-click Excel-with-native-chart.

2026-04-18 UAT gap: when a user asks for "an Excel with the chart embedded",
the LLM previously had to produce a Python script for the user to run
locally, because excel_write writes styled xlsx (no chart) and chart_create
produces Plotly JSON (no openpyxl chart). This test suite covers bridging
those two by accepting an ``embed_chart`` parameter on excel_write that
names an existing chart in ``ctx.vars`` and synthesises an openpyxl native
chart embedded in the workbook.

Scope for v1:
- Support bar / line / pie chart types (by far the most common in finance)
- Skip scatter / heatmap / waterfall cleanly (no embed, no error)
- Derive x-column and y-column names from the Plotly JSON's axis titles
- Anchor the chart to the right of the data (one-column spacer)
- Title comes from the Plotly title.text field
- Missing chart name → clear error message with list of available charts
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.excel_write import (
    ExcelWriteInput,
    ExcelWriteTool,
    _chart_spec_from_plotly_json,
)


# ---------------------------------------------------------------------------
# Pure helper: parse Plotly JSON → openpyxl-ready spec dict
# ---------------------------------------------------------------------------

def test_chart_spec_from_plotly_bar():
    df = pd.DataFrame(
        {"region": ["Americas", "EMEA", "APAC"], "total_revenue": [138, 82, 62]}
    )
    fig = px.bar(df, x="region", y="total_revenue", title="Total Revenue by Region")
    spec = _chart_spec_from_plotly_json(fig.to_json())
    assert spec is not None
    assert spec["kind"] == "bar"
    assert spec["x_col"] == "region"
    assert spec["y_col"] == "total_revenue"
    assert spec["title"] == "Total Revenue by Region"


def test_chart_spec_from_plotly_line():
    df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "sales": [10, 20, 30]})
    fig = px.line(df, x="month", y="sales", title="Monthly Sales")
    spec = _chart_spec_from_plotly_json(fig.to_json())
    assert spec is not None
    assert spec["kind"] == "line"
    assert spec["x_col"] == "month"
    assert spec["y_col"] == "sales"


def test_chart_spec_from_plotly_pie():
    """Pie is a different shape: uses 'labels' + 'values' not x/y."""
    df = pd.DataFrame({"segment": ["A", "B", "C"], "count": [10, 20, 30]})
    fig = px.pie(df, names="segment", values="count", title="Segment Share")
    spec = _chart_spec_from_plotly_json(fig.to_json())
    assert spec is not None
    assert spec["kind"] == "pie"
    # Pie uses labels/values — we normalise to x_col (categories) / y_col (numeric)
    assert spec["x_col"] == "segment"
    assert spec["y_col"] == "count"


def test_chart_spec_returns_none_for_unsupported_types():
    """Heatmap / scatter3d / waterfall — types openpyxl doesn't natively
    support — return None so excel_write can skip embed with a note rather
    than erroring."""
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    fig = px.scatter_3d(df, x="x", y="y", z="y")
    spec = _chart_spec_from_plotly_json(fig.to_json())
    assert spec is None


def test_chart_spec_returns_none_for_garbage_input():
    assert _chart_spec_from_plotly_json("{}") is None
    assert _chart_spec_from_plotly_json("not json") is None
    assert _chart_spec_from_plotly_json('{"data": []}') is None


# ---------------------------------------------------------------------------
# Integration: excel_write + embed_chart produces xlsx with openpyxl Chart
# ---------------------------------------------------------------------------

def _make_ctx_with_data_and_chart(tmp_path: Path) -> SessionContext:
    """Prepare a SessionContext with a revenue DataFrame + a bar chart over it."""
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    df = pd.DataFrame(
        {"region": ["Americas", "EMEA", "APAC"], "total_revenue": [13_800_000, 8_260_000, 6_280_000]}
    )
    ctx.vars.set("revenue_by_region", df)
    fig = px.bar(df, x="region", y="total_revenue", title="Total Revenue by Region")
    ctx.vars.set("rev_chart", fig.to_json(), var_type="chart")
    return ctx


async def test_embed_chart_adds_native_chart_to_xlsx(tmp_path):
    """Happy path: after excel_write with embed_chart, the produced xlsx
    contains an openpyxl native Chart object (not a raster image)."""
    ctx = _make_ctx_with_data_and_chart(tmp_path)
    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="revenue_by_region",
            sheet_name="Revenue",
            embed_chart="rev_chart",
        ),
        ctx,
    )
    assert not result.is_error, f"tool errored: {result.content}"

    # The artifact result must surface the path so the channel adapter can
    # deliver it — same shape as other excel_write outputs.
    path = Path(result.content["path"])
    assert path.exists()
    assert path.suffix == ".xlsx"

    # Open the produced xlsx and inspect: the Revenue sheet must contain
    # exactly one native chart.
    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb["Revenue"]
    assert len(ws._charts) == 1, f"expected 1 embedded chart, found {len(ws._charts)}"
    chart = ws._charts[0]
    # openpyxl BarChart carries a title object
    title_obj = chart.title
    assert title_obj is not None
    # Plotly-sourced title must survive to the native chart title
    title_text = _extract_openpyxl_title(title_obj)
    assert "Total Revenue by Region" in title_text


def _extract_openpyxl_title(title_obj) -> str:
    """openpyxl Chart.title can be str or a Title object with nested rich text."""
    if isinstance(title_obj, str):
        return title_obj
    # Title.tx.rich.p[0].r[0].t shape
    try:
        return "".join(
            run.t
            for p in title_obj.tx.rich.p
            for run in p.r
        )
    except Exception:
        return str(title_obj)


async def test_embed_chart_missing_name_returns_error(tmp_path):
    """Unknown chart name → clear, actionable error. Must include the list
    of available chart names so the LLM can self-correct."""
    ctx = _make_ctx_with_data_and_chart(tmp_path)
    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="revenue_by_region",
            sheet_name="Revenue",
            embed_chart="chart_that_does_not_exist",
        ),
        ctx,
    )
    assert result.is_error
    assert "chart_that_does_not_exist" in result.content
    # Error should list the available chart names to help the LLM retry
    assert "rev_chart" in result.content


async def test_embed_chart_unsupported_type_skips_without_error(tmp_path):
    """If the named chart is a type we can't translate (heatmap, scatter_3d,
    etc.), the tool must NOT error out — it still produces the xlsx with
    the data, just without an embedded chart. The result content should
    flag that the embed was skipped so the LLM can narrate it honestly."""
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3], "z": [1, 2, 3]})
    ctx.vars.set("data", df)
    fig = px.scatter_3d(df, x="x", y="y", z="z")
    ctx.vars.set("bad_chart", fig.to_json(), var_type="chart")

    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="data",
            sheet_name="D",
            embed_chart="bad_chart",
        ),
        ctx,
    )
    assert not result.is_error, f"should not error, got: {result.content}"
    # Honest: the result surfaces that the embed was skipped + a reason
    # the LLM can narrate to the user.
    assert result.content.get("embed_chart_skipped") is True
    assert "embed_chart_skip_reason" in result.content
    assert result.content["embed_chart_skip_reason"]  # non-empty


async def test_embed_chart_none_keeps_current_behavior(tmp_path):
    """Regression: default path (no embed_chart) still produces xlsx
    without any chart. Matches pre-2026-04-18 behavior exactly."""
    ctx = _make_ctx_with_data_and_chart(tmp_path)
    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="revenue_by_region",
            sheet_name="Revenue",
            # embed_chart intentionally omitted
        ),
        ctx,
    )
    assert not result.is_error
    import openpyxl
    wb = openpyxl.load_workbook(Path(result.content["path"]))
    ws = wb["Revenue"]
    assert len(ws._charts) == 0


async def test_embed_chart_with_unknown_columns_skips_embed(tmp_path):
    """If the chart references columns that aren't in the DataFrame being
    written (e.g. LLM changed the var between chart_create and
    excel_write), skip the embed cleanly with a note — don't write a
    broken chart pointing at cells that don't exist."""
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    # DataFrame has region + total_revenue
    df = pd.DataFrame({"region": ["A", "B"], "total_revenue": [1, 2]})
    ctx.vars.set("data", df)
    # But chart was made over a different schema
    other_df = pd.DataFrame({"category": ["X", "Y"], "amount": [10, 20]})
    fig = px.bar(other_df, x="category", y="amount", title="Wrong schema chart")
    ctx.vars.set("wrong_chart", fig.to_json(), var_type="chart")

    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="data",
            sheet_name="D",
            embed_chart="wrong_chart",
        ),
        ctx,
    )
    assert not result.is_error
    # Flag the skip so the LLM can narrate honestly
    assert result.content.get("embed_chart_skipped") is True


async def test_embed_chart_dry_run_does_not_touch_disk(tmp_path):
    """dry_run must NOT write any file regardless of embed_chart setting.
    Matches the existing excel_write dry_run contract."""
    ctx = _make_ctx_with_data_and_chart(tmp_path)
    ctx.dry_run = True
    tool = ExcelWriteTool()
    result = await tool.execute(
        ExcelWriteInput(
            input_var="revenue_by_region",
            sheet_name="Revenue",
            embed_chart="rev_chart",
        ),
        ctx,
    )
    assert not result.is_error
    # DryRunReceipt in content, not a path
    from yigthinker.types import DryRunReceipt
    assert isinstance(result.content, DryRunReceipt)
    # No xlsx files in tmp_path — strictly nothing written
    assert not list(tmp_path.rglob("*.xlsx"))
