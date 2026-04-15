import pytest
import pandas as pd
from yigthinker.tools.dataframe.df_transform import DfTransformTool, DfTransformInput
from yigthinker.session import SessionContext


@pytest.fixture
def ctx():
    c = SessionContext()
    c.vars.set("df1", pd.DataFrame({"a": [1, 2, 3]}))
    return c


@pytest.fixture
def tool():
    return DfTransformTool()


@pytest.mark.asyncio
async def test_getattr_blocks_dunder_access(tool, ctx):
    """getattr must not allow access to dunder attributes via indirect reference.

    Uses a list-index expression so the AST checker cannot evaluate the name
    at parse time — the attribute name '_metadata' is not in _BLOCKED_DUNDERS
    so visit_Constant does not flag the literal; the call reaches _safe_getattr
    at runtime where the leading underscore causes the block.
    """
    inp = DfTransformInput(
        code='names = ["_metadata"]\nresult = getattr([], names[0])',
        input_var="df1",
        output_var="out",
    )
    r = await tool.execute(inp, ctx)
    assert r.is_error
    assert "private" in r.content.lower() or "blocked" in r.content.lower()


@pytest.mark.asyncio
async def test_getattr_blocks_concatenated_dunder(tool, ctx):
    """String concatenation to build dunder names must be blocked at runtime."""
    inp = DfTransformInput(
        code='x = "__" + "class__"\nresult = getattr([], x)',
        input_var="df1",
        output_var="out",
    )
    r = await tool.execute(inp, ctx)
    assert r.is_error
    assert "private" in r.content.lower() or "blocked" in r.content.lower()


@pytest.mark.asyncio
async def test_getattr_allows_normal_attributes(tool, ctx):
    """Normal attribute access via getattr must still work."""
    inp = DfTransformInput(
        code='result = getattr(df, "head")()',
        input_var="df1",
        output_var="out",
    )
    r = await tool.execute(inp, ctx)
    assert not r.is_error


@pytest.mark.asyncio
async def test_normal_transform_still_works(tool, ctx):
    """Basic transforms must not be broken by sandbox hardening."""
    inp = DfTransformInput(
        code="result = df[df['a'] > 1]",
        input_var="df1",
        output_var="out",
    )
    r = await tool.execute(inp, ctx)
    assert not r.is_error
    assert "out" in ctx.vars
