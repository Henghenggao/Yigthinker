# Regression: ISSUE-001 -- import statement fails inside df_transform sandbox
# Found by /qa on 2026-04-07
# Root cause: __import__ was placed in namespace dict, not in __builtins__ dict.
#   Python's `import X` statement looks up __import__ from __builtins__, not
#   from the exec namespace. So `import pandas as pd` raised NameError.
# Fix: moved __import__: _safe_import into the __builtins__ dict (sandbox_builtins).

import pandas as pd
import pytest
from yigthinker.tools.dataframe.df_transform import DfTransformTool
from yigthinker.session import SessionContext


@pytest.fixture
def ctx_with_df():
    ctx = SessionContext()
    ctx.vars.set("data", pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}))
    return ctx


async def test_import_pandas_works_in_sandbox(ctx_with_df):
    """import pandas as pd should work because _safe_import allows it."""
    tool = DfTransformTool()
    code = "import pandas as pd\nresult = pd.DataFrame({'x': [1]})"
    input_obj = tool.input_schema(code=code, input_var="data", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error, f"Expected success, got: {result.content}"
    df = ctx_with_df.vars.get("out")
    assert list(df.columns) == ["x"]


async def test_import_numpy_works_in_sandbox(ctx_with_df):
    """import numpy as np should work."""
    tool = DfTransformTool()
    code = "import numpy as np\nresult = pd.DataFrame({'mean': [np.mean(df['a'])]})"
    input_obj = tool.input_schema(code=code, input_var="data", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error, f"Expected success, got: {result.content}"
    df = ctx_with_df.vars.get("out")
    assert df["mean"].iloc[0] == 2.0


async def test_import_os_still_blocked(ctx_with_df):
    """import os must still be blocked by _safe_import whitelist."""
    tool = DfTransformTool()
    code = "import os\nresult = df"
    input_obj = tool.input_schema(code=code, input_var="data", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error
    assert "not allowed" in result.content.lower() or "import" in result.content.lower()


async def test_import_subprocess_blocked(ctx_with_df):
    """import subprocess must be blocked -- sandbox escape vector."""
    tool = DfTransformTool()
    code = "import subprocess\nresult = df"
    input_obj = tool.input_schema(code=code, input_var="data", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert result.is_error


async def test_preinjected_pd_still_works_without_import(ctx_with_df):
    """pd is pre-injected; code that uses pd without import should still work."""
    tool = DfTransformTool()
    code = "result = pd.DataFrame({'sum': [df['a'].sum()]})"
    input_obj = tool.input_schema(code=code, input_var="data", output_var="out")
    result = await tool.execute(input_obj, ctx_with_df)
    assert not result.is_error
    df = ctx_with_df.vars.get("out")
    assert df["sum"].iloc[0] == 6
