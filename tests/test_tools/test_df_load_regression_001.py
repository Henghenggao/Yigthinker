# Regression: ISSUE-002 -- df_load missing header/skiprows/usecols parameters
# Found by /qa on 2026-04-07
# Root cause: DfLoadInput only had source, var_name, sheet_name. Files without
#   standard headers (SAP BPC exports, raw sensor data) forced an extra
#   df_transform round-trip just to rename columns and drop metadata rows.
# Fix: added header (int|None), skiprows (int|None), usecols (str|None) to
#   DfLoadInput, wired into the loader kwargs for CSV/Excel only (not JSON/Parquet).

import json
import pytest
from yigthinker.tools.dataframe.df_load import DfLoadTool
from yigthinker.session import SessionContext


@pytest.fixture
def csv_no_header(tmp_path):
    """CSV file without a header row."""
    path = tmp_path / "raw.csv"
    path.write_text("Alice,90\nBob,85\nCharlie,77\n")
    return path


@pytest.fixture
def csv_with_skiprows(tmp_path):
    """CSV with 2 metadata rows before the real header."""
    path = tmp_path / "meta.csv"
    path.write_text("Report Title\nGenerated 2026-04-07\nname,score\nAlice,90\nBob,85\n")
    return path


@pytest.fixture
def json_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([{"x": 1}, {"x": 2}]))
    return path


async def test_header_none_loads_without_header(csv_no_header, tmp_path):
    """header=None should load CSV without treating first row as header."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        source=str(csv_no_header), var_name="raw", header=None,
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, f"Failed: {result.content}"
    df = ctx.vars.get("raw")
    assert len(df) == 3  # all 3 rows are data, none consumed as header
    assert list(df.columns) == [0, 1]  # positional column names


async def test_skiprows_skips_metadata(csv_with_skiprows, tmp_path):
    """skiprows=2 should skip the two metadata rows."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        source=str(csv_with_skiprows), var_name="clean", skiprows=2,
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, f"Failed: {result.content}"
    df = ctx.vars.get("clean")
    assert list(df.columns) == ["name", "score"]
    assert len(df) == 2


async def test_usecols_selects_columns_excel_syntax(tmp_path):
    """usecols='A:B' (Excel range string) should work for .xlsx files.

    For CSV, usecols needs a list (handled by df_transform post-load).
    The primary use case for usecols is Excel files with empty trailing columns.
    """
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "score", "junk1", "junk2"])
    ws.append(["Alice", 90, "", ""])
    ws.append(["Bob", 85, "", ""])
    path = tmp_path / "wide.xlsx"
    wb.save(path)

    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        source=str(path), var_name="narrow", usecols="A:B",
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, f"Failed: {result.content}"
    df = ctx.vars.get("narrow")
    assert list(df.columns) == ["name", "score"]
    assert len(df) == 2


async def test_json_ignores_header_param(json_file, tmp_path):
    """JSON loader must not receive header kwarg -- it would crash."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    # header defaults to 0, but should NOT be passed to read_json
    input_obj = tool.input_schema(source=str(json_file), var_name="j")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, f"JSON load failed: {result.content}"
    df = ctx.vars.get("j")
    assert len(df) == 2


async def test_json_with_explicit_header_none_still_works(json_file, tmp_path):
    """Even if LLM sends header=null for a JSON file, it should not crash."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(source=str(json_file), var_name="j2", header=None)
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, f"JSON load with header=None failed: {result.content}"


async def test_default_header_zero_preserves_csv_behavior(tmp_path):
    """Default header=0 should behave identically to vanilla pd.read_csv."""
    path = tmp_path / "normal.csv"
    path.write_text("col_a,col_b\n1,2\n3,4\n")
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(source=str(path), var_name="normal")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    df = ctx.vars.get("normal")
    assert list(df.columns) == ["col_a", "col_b"]
    assert len(df) == 2


async def test_relative_path_resolves_within_workspace(tmp_path):
    """Relative paths are anchored to workspace_dir, not the process cwd."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "inside.csv"
    path.write_text("name,score\nAlice,90\n")

    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(workspace)})
    input_obj = tool.input_schema(source="inside.csv", var_name="inside")
    result = await tool.execute(input_obj, ctx)

    assert not result.is_error, result.content
    df = ctx.vars.get("inside")
    assert list(df.columns) == ["name", "score"]


async def test_relative_parent_path_outside_workspace_is_blocked(tmp_path):
    """Relative ../ paths must not escape workspace_dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("name,score\nMallory,100\n")

    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(workspace)})
    input_obj = tool.input_schema(source="../secret.csv", var_name="blocked")
    result = await tool.execute(input_obj, ctx)

    assert result.is_error
    assert "outside the workspace directory" in str(result.content)
