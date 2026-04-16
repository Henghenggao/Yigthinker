import json
import pandas as pd
import pytest
from yigthinker.tools.dataframe.df_load import DfLoadTool, _safe_path
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


@pytest.fixture
def xlsx_multi_sheet(tmp_path):
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"product": ["A", "B"], "revenue": [100, 200]}).to_excel(
            writer, sheet_name="Revenue", index=False,
        )
        pd.DataFrame({"item": ["X"], "cost": [50]}).to_excel(
            writer, sheet_name="Costs", index=False,
        )
    return path


@pytest.fixture
def xlsx_single_sheet(tmp_path):
    path = tmp_path / "single.xlsx"
    pd.DataFrame({"col1": [1, 2], "col2": [3, 4]}).to_excel(
        path, sheet_name="Sheet1", index=False,
    )
    return path


async def test_load_csv(csv_file, tmp_path):
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(source=str(csv_file), var_name="scores")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "scores" in ctx.vars
    df = ctx.vars.get("scores")
    assert list(df.columns) == ["name", "score"]
    assert len(df) == 2


async def test_load_json(json_file, tmp_path):
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
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


async def test_load_excel_multi_sheet_enumerates_sheets(xlsx_multi_sheet, tmp_path):
    """Multi-sheet Excel without sheet_name returns available sheets for LLM selection."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(source=str(xlsx_multi_sheet), var_name="data")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert isinstance(result.content, dict)
    assert result.content["available_sheets"] == ["Revenue", "Costs"]
    assert "data" not in ctx.vars  # nothing loaded yet


async def test_load_excel_single_sheet_loads_directly(xlsx_single_sheet, tmp_path):
    """Single-sheet Excel without sheet_name loads that sheet directly."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(source=str(xlsx_single_sheet), var_name="data")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "data" in ctx.vars
    df = ctx.vars.get("data")
    assert list(df.columns) == ["col1", "col2"]
    assert len(df) == 2


async def test_load_excel_wrong_sheet_name_shows_available(xlsx_multi_sheet, tmp_path):
    """Wrong sheet_name returns error listing available sheets."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        source=str(xlsx_multi_sheet), var_name="data", sheet_name="Nonexistent",
    )
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
    assert "Revenue" in str(result.content)
    assert "Costs" in str(result.content)


async def test_load_excel_correct_sheet_name(xlsx_multi_sheet, tmp_path):
    """Explicit sheet_name loads that sheet correctly."""
    tool = DfLoadTool()
    ctx = SessionContext(settings={"workspace_dir": str(tmp_path)})
    input_obj = tool.input_schema(
        source=str(xlsx_multi_sheet), var_name="rev", sheet_name="Revenue",
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "rev" in ctx.vars
    df = ctx.vars.get("rev")
    assert list(df.columns) == ["product", "revenue"]
    assert len(df) == 2


# --- Quick 260416-fs1: attachment allowlist for _safe_path ---


def test_safe_path_accepts_workspace_relative(tmp_path):
    """Workspace-relative paths resolve inside workspace (existing behavior)."""
    settings = {"workspace_dir": str(tmp_path)}
    resolved, err = _safe_path("sub/file.csv", settings)
    assert err is None
    assert resolved == (tmp_path / "sub" / "file.csv").resolve()


def test_safe_path_rejects_outside_workspace(tmp_path):
    """Absolute paths outside workspace_dir are rejected (existing behavior)."""
    settings = {"workspace_dir": str(tmp_path)}
    other = tmp_path.parent / "elsewhere.csv"
    resolved, err = _safe_path(str(other), settings)
    assert err is not None
    assert "Access denied" in err


def test_safe_path_accepts_allowlisted_outside_workspace(tmp_path):
    """Path outside workspace is accepted when present in attachments allowlist."""
    settings = {"workspace_dir": str(tmp_path)}
    outside = tmp_path.parent / "teams_tmp" / "data.xlsx"
    allowlist = {outside.resolve()}
    resolved, err = _safe_path(str(outside), settings, attachments=allowlist)
    assert err is None
    assert resolved == outside.resolve()


def test_safe_path_still_rejects_non_allowlisted_outside(tmp_path):
    """Unrelated allowlist entries do not whitelist a different outside path."""
    settings = {"workspace_dir": str(tmp_path)}
    outside = tmp_path.parent / "not_allowlisted.xlsx"
    unrelated = {(tmp_path.parent / "something_else.xlsx").resolve()}
    resolved, err = _safe_path(str(outside), settings, attachments=unrelated)
    assert err is not None
    assert "Access denied" in err


def test_safe_path_allowlist_none_preserves_existing_behavior(tmp_path):
    """Explicit attachments=None behaves identically to the pre-allowlist signature."""
    settings = {"workspace_dir": str(tmp_path)}
    outside = tmp_path.parent / "x.csv"
    resolved, err = _safe_path(str(outside), settings, attachments=None)
    assert err is not None
    assert "Access denied" in err
