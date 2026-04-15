"""Tests for df_transform multi-variable input (Task 19)."""
from __future__ import annotations

import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.dataframe.df_transform import (
    DfTransformInput,
    DfTransformTool,
)


@pytest.mark.asyncio
async def test_multi_variable_access():
    ctx = SessionContext()
    ctx.vars.set(
        "sales", pd.DataFrame({"region": ["US", "EU"], "amount": [100, 200]})
    )
    ctx.vars.set(
        "targets", pd.DataFrame({"region": ["US", "EU"], "target": [120, 180]})
    )

    tool = DfTransformTool()
    inp = DfTransformInput(
        code="merged = pd.merge(sales, targets, on='region')\nresult = merged",
        input_var="sales",
        output_var="comparison",
        extra_vars=["targets"],
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, f"Multi-var failed: {result.content}"

    comparison = ctx.vars.get("comparison")
    assert "target" in comparison.columns
    assert len(comparison) == 2


@pytest.mark.asyncio
async def test_missing_extra_var_returns_error():
    ctx = SessionContext()
    ctx.vars.set("a", pd.DataFrame({"x": [1]}))

    tool = DfTransformTool()
    inp = DfTransformInput(
        code="result = a",
        input_var="a",
        output_var="out",
        extra_vars=["nonexistent_var"],
    )
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "nonexistent_var" in str(result.content)


@pytest.mark.asyncio
async def test_extra_vars_empty_default_still_works():
    """Backwards compat: no extra_vars still exposes df and input_var name."""
    ctx = SessionContext()
    ctx.vars.set("sales", pd.DataFrame({"x": [1, 2, 3]}))

    tool = DfTransformTool()
    inp = DfTransformInput(
        code="result = sales[sales['x'] > 1]",
        input_var="sales",
        output_var="filtered",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, result.content
    assert len(ctx.vars.get("filtered")) == 2


@pytest.mark.asyncio
async def test_df_alias_still_works():
    """The implicit 'df' binding remains for codes that use it."""
    ctx = SessionContext()
    ctx.vars.set("my_df", pd.DataFrame({"x": [1, 2, 3]}))
    tool = DfTransformTool()
    inp = DfTransformInput(
        code="result = df[df['x'] < 3]",
        input_var="my_df",
        output_var="out",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error, result.content
    assert len(ctx.vars.get("out")) == 2
