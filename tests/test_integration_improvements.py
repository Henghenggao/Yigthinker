"""Smoke tests for LangAlpha-inspired improvements (Task 22).

End-to-end verification that the key pieces of the plan — sandbox,
chart pipeline, steering queue, and leak detection — work together on a
realistic workflow.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.dataframe.df_transform import (
    DfTransformInput,
    DfTransformTool,
)
from yigthinker.tools.visualization.chart_create import (
    ChartCreateInput,
    ChartCreateTool,
)


@pytest.fixture
def ctx():
    c = SessionContext()
    c.vars.set("data", pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]}))
    return c


@pytest.mark.asyncio
async def test_sandbox_then_chart_then_export(ctx):
    """Full pipeline: transform -> chart -> optional PNG export."""
    # 1. Transform: filter the registered DataFrame.
    tool = DfTransformTool()
    inp = DfTransformInput(
        code="result = df[df['x'] > 1]",
        input_var="data",
        output_var="filtered",
    )
    r = await tool.execute(inp, ctx)
    assert not r.is_error, r.content
    assert "filtered" in ctx.vars
    assert len(ctx.vars.get("filtered")) == 2

    # 2. Chart: build a bar chart from the filtered DataFrame.
    chart_tool = ChartCreateTool()
    chart_inp = ChartCreateInput(
        var_name="filtered",
        chart_type="bar",
        x="x",
        y="y",
        chart_name="test_chart",
    )
    r2 = await chart_tool.execute(chart_inp, ctx)
    assert not r2.is_error, r2.content
    assert "test_chart" in ctx.vars
    # chart JSON must be valid and contain a bar trace
    parsed = json.loads(r2.content["chart_json"])
    assert parsed["data"][0]["type"] == "bar"

    # 3. Export to PNG (optional — skip when kaleido is missing).
    try:
        from yigthinker.visualization.exporter import ChartExporter  # noqa: WPS433
    except ImportError:
        pytest.skip("ChartExporter / kaleido not available")
        return

    chart_json = ctx.vars.get("test_chart")
    try:
        png = ChartExporter().to_png(chart_json)
    except Exception as exc:  # kaleido missing or Chromium unavailable
        pytest.skip(f"PNG export unavailable: {exc}")
        return
    assert png[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_multi_var_transform_then_waterfall_and_docx(tmp_path):
    """Multi-DataFrame merge -> waterfall chart -> DOCX report."""
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    ctx.vars.set(
        "pnl",
        pd.DataFrame({
            "line": ["Revenue", "COGS", "Gross Profit", "OpEx", "Net Income"],
            "amount": [1000, -400, 600, -300, 300],
        }),
    )

    # Waterfall chart covers Task 17.
    chart_tool = ChartCreateTool()
    chart_inp = ChartCreateInput(
        var_name="pnl",
        chart_type="waterfall",
        x="line",
        y="amount",
        chart_name="bridge",
    )
    r = await chart_tool.execute(chart_inp, ctx)
    assert not r.is_error, r.content

    # DOCX report covers Task 18.
    from yigthinker.tools.reports.report_generate import (
        ReportGenerateInput,
        ReportGenerateTool,
    )
    report_tool = ReportGenerateTool()
    out_path = tmp_path / "pnl.docx"
    r2 = await report_tool.execute(
        ReportGenerateInput(
            var_name="pnl",
            format="docx",
            output_path=str(out_path),
            title="P&L Report",
        ),
        ctx,
    )
    assert not r2.is_error, r2.content
    assert out_path.exists() and out_path.stat().st_size > 1000


def test_steering_queue_roundtrip():
    """Steering messages survive enqueue/drain cycle and ordering is preserved."""
    ctx = SessionContext()
    ctx.steer("focus on Q4")
    ctx.steer("ignore marketing data")
    msgs = ctx.drain_steerings()
    assert msgs == ["focus on Q4", "ignore marketing data"]
    assert ctx.drain_steerings() == []


def test_leak_detection_standalone():
    """Leak detector catches API keys in content."""
    fake_key = "sk-testkey1234567890abcdef1234567890"
    with patch.dict(os.environ, {"OPENAI_API_KEY": fake_key}):
        from yigthinker.hooks.leak_detection import LeakDetector
        d = LeakDetector()
        redacted, hits = d.scan(f"key is {fake_key}")
        assert fake_key not in redacted
        assert any("OPENAI" in h or "API_KEY" in h for h in hits)


def test_var_registry_memory_limit_catches_oversized_df():
    """Task 16 plugs into the end-to-end flow: tight limit rejects big DFs."""
    import numpy as np

    from yigthinker.session import VarRegistry

    reg = VarRegistry(max_bytes=1_000_000)
    big = pd.DataFrame(np.random.randn(200_000, 1), columns=["x"])  # ~1.6MB
    with pytest.raises(MemoryError):
        reg.set("too_big", big)


def test_quoted_message_dataclass_in_session_module():
    """Task 13/14 types are reachable from the public session module."""
    from yigthinker.session import MessageIdMap, QuotedMessage

    q = QuotedMessage(original_id="m1", original_text="hello", original_role="user")
    assert q.original_id == "m1"
    assert q.original_text == "hello"
    assert q.original_role == "user"
    assert q.history_index is None

    m = MessageIdMap()
    m.record("platform-msg-1", 7)
    assert m.get_history_index("platform-msg-1") == 7
    assert m.get_history_index("missing") is None
