import pandas as pd
import pytest
from yigthinker.tools.dataframe.df_transform import DfTransformTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_df():
    ctx = SessionContext()
    ctx.vars.set("sales", pd.DataFrame({"amount": [100, 200, 300], "region": ["N", "S", "N"]}))
    return ctx


async def test_transform_filter(ctx_with_df):
    tool = DfTransformTool()
    code = "result = df[df['region'] == 'N']"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="north_sales")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error
    df = ctx_with_df.vars.get("north_sales")
    assert len(df) == 2


async def test_transform_aggregation(ctx_with_df):
    tool = DfTransformTool()
    code = "result = df.groupby('region')['amount'].sum().reset_index()"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="by_region")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error
    df = ctx_with_df.vars.get("by_region")
    assert "amount" in df.columns


async def test_sandbox_blocks_file_io(ctx_with_df):
    tool = DfTransformTool()
    code = "import os; result = df"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error
    assert "not allowed" in result.content.lower() or "import" in result.content.lower()


async def test_sandbox_blocks_open(ctx_with_df):
    tool = DfTransformTool()
    code = "result = open('/etc/passwd').read()"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error


async def test_sandbox_blocks_pandas_readers(ctx_with_df):
    tool = DfTransformTool()
    code = "result = pd.read_csv('https://example.com/data.csv')"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error
    assert "blocked" in result.content.lower()


async def test_sandbox_blocks_dataframe_writers(ctx_with_df):
    tool = DfTransformTool()
    code = "result = df.to_csv('leak.csv')"
    input_obj = tool.input_schema(code=code, input_var="sales", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error
    assert "blocked" in result.content.lower()


async def test_missing_input_var_returns_error():
    tool = DfTransformTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(code="result = df", input_var="nonexistent", output_var="out")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
    assert "nonexistent" in result.content
