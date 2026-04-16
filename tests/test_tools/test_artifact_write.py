"""Tests for artifact_write tool.

The artifact_write tool gives the LLM a first-class path to persist free-form
text (scripts, configs, markdown) without abusing df_transform/df_load to stash
source code inside a DataFrame. See .planning/quick/260416-j3y-*.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yigthinker.session import SessionContext
from yigthinker.tools.artifact_write import (
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_BYTES,
    ArtifactWriteTool,
)


def _make_ctx(tmp_path: Path) -> SessionContext:
    return SessionContext(settings={"workspace_dir": str(tmp_path)})


async def test_writes_simple_python_script(tmp_path):
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)
    script = "import pandas as pd\n\nprint('hi')\n"
    input_obj = tool.input_schema(
        filename="build_pl_sheet.py",
        content=script,
        summary="Builds formatted P&L sheet",
    )
    result = await tool.execute(input_obj, ctx)

    assert not result.is_error, result.content
    out_path = tmp_path / "build_pl_sheet.py"
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == script

    assert isinstance(result.content, dict)
    assert result.content["kind"] == "file"
    assert result.content["filename"] == "build_pl_sheet.py"
    assert result.content["bytes"] == len(script.encode("utf-8"))
    assert result.content["summary"] == "Builds formatted P&L sheet"
    assert Path(result.content["path"]).resolve() == out_path.resolve()


async def test_writes_nested_directory(tmp_path):
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)
    input_obj = tool.input_schema(
        filename="scripts/reports/pl.py",
        content="pass\n",
    )
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error, result.content
    assert (tmp_path / "scripts" / "reports" / "pl.py").exists()


async def test_rejects_path_outside_workspace(tmp_path):
    tool = ArtifactWriteTool()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ctx = SessionContext(settings={"workspace_dir": str(workspace)})

    input_obj = tool.input_schema(
        filename="../leaked.py",
        content="# oops\n",
    )
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
    assert "outside workspace" in str(result.content)


async def test_refuses_binary_extension():
    # Pydantic validator must reject disallowed extensions up-front
    tool = ArtifactWriteTool()
    with pytest.raises(Exception):  # pydantic ValidationError
        tool.input_schema(filename="evil.exe", content="X")


async def test_allowed_extensions_cover_common_cases():
    # Sanity: the allowlist includes the extensions the LLM is most likely to need
    for ext in [".py", ".sql", ".md", ".txt", ".yaml", ".json", ".sh", ".toml"]:
        assert ext in ALLOWED_EXTENSIONS


async def test_refuses_oversized_content(tmp_path):
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)
    big = "x" * (MAX_CONTENT_BYTES + 1)
    input_obj = tool.input_schema(filename="big.txt", content=big)
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
    assert "too large" in str(result.content).lower()


async def test_overwrite_defaults_to_false(tmp_path):
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)

    first = tool.input_schema(filename="x.py", content="a = 1\n")
    r1 = await tool.execute(first, ctx)
    assert not r1.is_error, r1.content

    second = tool.input_schema(filename="x.py", content="a = 2\n")
    r2 = await tool.execute(second, ctx)
    assert r2.is_error
    assert "exists" in str(r2.content).lower()
    # Original content preserved
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == "a = 1\n"


async def test_overwrite_true_replaces_existing(tmp_path):
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)

    r1 = await tool.execute(
        tool.input_schema(filename="x.py", content="a = 1\n"), ctx
    )
    assert not r1.is_error
    r2 = await tool.execute(
        tool.input_schema(filename="x.py", content="a = 2\n", overwrite=True), ctx
    )
    assert not r2.is_error, r2.content
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == "a = 2\n"


async def test_registers_path_in_attachments(tmp_path):
    """Written artifact should join ctx.attachments so IM adapters can reuse it."""
    tool = ArtifactWriteTool()
    ctx = _make_ctx(tmp_path)
    result = await tool.execute(
        tool.input_schema(filename="report.md", content="# Hi\n"), ctx
    )
    assert not result.is_error
    written = (tmp_path / "report.md").resolve()
    assert written in ctx.attachments


async def test_tool_metadata():
    tool = ArtifactWriteTool()
    assert tool.name == "artifact_write"
    # Description must steer LLM to this tool instead of df_transform for text
    assert "text" in tool.description.lower() or "script" in tool.description.lower()
