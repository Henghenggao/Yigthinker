import pandas as pd
import pytest
from yigthinker.tools.dataframe.df_merge import DfMergeTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_two_dfs():
    ctx = SessionContext()
    orders = pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [10, 11, 10], "amount": [100, 200, 150]})
    customers = pd.DataFrame({"customer_id": [10, 11], "name": ["Alice", "Bob"]})
    ctx.vars.set("orders", orders)
    ctx.vars.set("customers", customers)
    return ctx


async def test_inner_join(ctx_with_two_dfs):
    tool = DfMergeTool()
    input_obj = tool.input_schema(
        left_var="orders", right_var="customers",
        on="customer_id", how="inner", output_var="merged"
    )
    result = await tool.execute(input_obj, ctx_with_two_dfs)
    assert not result.is_error
    df = ctx_with_two_dfs.vars.get("merged")
    assert "name" in df.columns
    assert "amount" in df.columns
    assert len(df) == 3


async def test_auto_key_inference(ctx_with_two_dfs):
    tool = DfMergeTool()
    input_obj = tool.input_schema(
        left_var="orders", right_var="customers", output_var="auto_merged"
    )
    result = await tool.execute(input_obj, ctx_with_two_dfs)
    assert not result.is_error
    df = ctx_with_two_dfs.vars.get("auto_merged")
    assert "name" in df.columns


async def test_missing_var_returns_error():
    tool = DfMergeTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(left_var="a", right_var="b", output_var="c")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
