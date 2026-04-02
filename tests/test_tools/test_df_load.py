import csv
import json
from pathlib import Path
import pytest
from yigthinker.tools.dataframe.df_load import DfLoadTool
from yigthinker.session import SessionContext


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("name,score\nAlice,90\nBob,85\n")
    return path


@pytest.fixture
def json_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([{"x": 1, "y": 2}, {"x": 3, "y": 4}]))
    return path


async def test_load_csv(csv_file):
    tool = DfLoadTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(source=str(csv_file), var_name="scores")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "scores" in ctx.vars
    df = ctx.vars.get("scores")
    assert list(df.columns) == ["name", "score"]
    assert len(df) == 2


async def test_load_json(json_file):
    tool = DfLoadTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(source=str(json_file), var_name="xy")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "xy" in ctx.vars


async def test_load_missing_file_returns_error():
    tool = DfLoadTool()
    ctx = SessionContext()
    input_obj = tool.input_schema(source="/nonexistent/file.csv", var_name="bad")
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
