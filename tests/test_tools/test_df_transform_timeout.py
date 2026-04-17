import pandas as pd
import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.dataframe.df_transform import DfTransformInput, DfTransformTool


@pytest.mark.slow
@pytest.mark.asyncio
async def test_infinite_loop_is_killed():
    """A user-provided infinite loop must be terminated by the timeout.

    Uses a 1-second override via ctx.settings so the test finishes quickly.
    The default timeout in production is 30 seconds.
    """
    ctx = SessionContext(settings={"df_transform": {"timeout": 1.0}})
    ctx.vars.set("df1", pd.DataFrame({"a": [1]}))
    tool = DfTransformTool()
    inp = DfTransformInput(
        code="while True: pass\nresult = df",
        input_var="df1",
        output_var="out",
    )
    result = await tool.execute(inp, ctx)
    assert result.is_error
    content = result.content if isinstance(result.content, str) else str(result.content)
    assert "timeout" in content.lower() or "timed out" in content.lower()


@pytest.mark.asyncio
async def test_quick_code_runs_under_timeout():
    """Normal code must not trigger the timeout path."""
    ctx = SessionContext(settings={"df_transform": {"timeout": 5.0}})
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2, 3]}))
    tool = DfTransformTool()
    inp = DfTransformInput(
        code="result = df",
        input_var="df1",
        output_var="out",
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    assert "out" in ctx.vars
