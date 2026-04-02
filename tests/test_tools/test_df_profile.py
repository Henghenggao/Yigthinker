import pandas as pd
import pytest
from yigthinker.tools.dataframe.df_profile import DfProfileTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_df():
    ctx = SessionContext()
    df = pd.DataFrame({
        "amount": [100.0, None, 300.0, 200.0, 150.0],
        "category": ["A", "B", "A", None, "B"],
    })
    ctx.vars.set("data", df)
    return ctx


async def test_profile_includes_missing_values(ctx_with_df):
    tool = DfProfileTool()
    input_obj = tool.input_schema(var_name="data")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error
    content = result.content
    assert "missing" in str(content).lower() or "null" in str(content).lower()


async def test_profile_includes_statistics(ctx_with_df):
    tool = DfProfileTool()
    input_obj = tool.input_schema(var_name="data")
    result = await tool.execute(input_obj, ctx_with_df)
    content = result.content
    assert "amount" in str(content)
    assert "mean" in str(content).lower() or "stats" in str(content).lower()


async def test_profile_missing_var_returns_error():
    tool = DfProfileTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(var_name="nonexistent")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
