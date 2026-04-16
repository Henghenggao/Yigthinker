"""Tests for structured_artifact_from_tool_result / choose_best_artifact.

Covers the kind="file" extension added for artifact_write (quick-260416-j3y).
"""
from __future__ import annotations

from yigthinker.channels.artifacts import (
    choose_best_artifact,
    structured_artifact_from_tool_result,
)


def test_file_artifact_detected_from_artifact_write_payload():
    raw = {
        "kind": "file",
        "path": "/tmp/workspace/build_pl_sheet.py",
        "filename": "build_pl_sheet.py",
        "bytes": 4321,
        "summary": "Builds formatted P&L sheet",
    }
    artifact = structured_artifact_from_tool_result(raw)
    assert artifact == {
        "kind": "file",
        "filename": "build_pl_sheet.py",
        "path": "/tmp/workspace/build_pl_sheet.py",
        "bytes": 4321,
        "summary": "Builds formatted P&L sheet",
    }


def test_file_artifact_requires_filename_and_path():
    # Missing filename → not recognized as a file artifact
    assert structured_artifact_from_tool_result(
        {"kind": "file", "path": "/tmp/x.py", "bytes": 1}
    ) is None
    # Missing path → same
    assert structured_artifact_from_tool_result(
        {"kind": "file", "filename": "x.py", "bytes": 1}
    ) is None


def test_file_artifact_accepts_null_summary():
    raw = {
        "kind": "file",
        "path": "/tmp/x.py",
        "filename": "x.py",
        "bytes": 0,
        "summary": None,
    }
    artifact = structured_artifact_from_tool_result(raw)
    assert artifact is not None
    assert artifact["summary"] is None
    assert artifact["bytes"] == 0


def test_chart_artifact_still_detected():
    # Sanity: existing chart detection is unchanged
    raw = {"chart_name": "Revenue", "chart_json": "{}"}
    artifact = structured_artifact_from_tool_result(raw)
    assert artifact == {
        "kind": "chart",
        "chart_name": "Revenue",
        "chart_json": "{}",
    }


def test_dataframe_preview_still_detected():
    raw = {
        "stored_as": "df1",
        "preview": {
            "type": "dataframe",
            "data": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        },
    }
    artifact = structured_artifact_from_tool_result(raw)
    assert artifact is not None
    assert artifact["kind"] == "table"
    assert artifact["columns"] == ["a", "b"]


def test_choose_best_prefers_chart_over_file():
    chart = {"kind": "chart", "chart_name": "c", "chart_json": "{}"}
    file_art = {
        "kind": "file", "filename": "x.py", "path": "/x.py",
        "bytes": 1, "summary": None,
    }
    assert choose_best_artifact([file_art, chart]) == chart


def test_choose_best_prefers_file_over_table():
    # File beats table: a saved script is usually the product, not the preview.
    file_art = {
        "kind": "file", "filename": "x.py", "path": "/x.py",
        "bytes": 1, "summary": None,
    }
    table = {
        "kind": "table", "title": "df1",
        "columns": ["a"], "rows": [[1]], "total_rows": 1,
    }
    assert choose_best_artifact([table, file_art]) == file_art


def test_choose_best_returns_most_recent_file_when_multiple():
    f1 = {"kind": "file", "filename": "a.py", "path": "/a.py", "bytes": 1, "summary": None}
    f2 = {"kind": "file", "filename": "b.py", "path": "/b.py", "bytes": 2, "summary": None}
    assert choose_best_artifact([f1, f2]) == f2
