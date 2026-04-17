"""Lock down artifact-delivery primitives used by Teams / Feishu / GChat adapters.

If these helpers regress, the end-to-end Excel delivery flow (Phase 0 fix)
will break even if the adapter send_response methods look correct.

See docs/superpowers/specs/2026-04-16-yigthinker-becomes-yigcore-design.md §2.
"""
from __future__ import annotations

import pytest


# ── structured_artifact_from_tool_result ────────────────────────────────────

def test_artifact_builder_recognizes_file_kind():
    """artifact_write returns {kind: 'file', ...} — helper must pass it through."""
    from yigthinker.channels.artifacts import structured_artifact_from_tool_result

    raw = {
        "kind": "file",
        "filename": "monthly_close.xlsx",
        "path": "/tmp/monthly_close.xlsx",
        "bytes": 9876,
        "summary": "April 2026 close workbook",
    }
    out = structured_artifact_from_tool_result(raw)
    assert out is not None
    assert out["kind"] == "file"
    assert out["filename"] == "monthly_close.xlsx"
    assert out["bytes"] == 9876


def test_artifact_builder_recognizes_chart_kind():
    """chart_create returns {chart_name, chart_json, ...}."""
    from yigthinker.channels.artifacts import structured_artifact_from_tool_result

    raw = {"chart_name": "revenue-trend", "chart_json": "{\"data\":[]}"}
    out = structured_artifact_from_tool_result(raw)
    assert out is not None
    assert out["kind"] == "chart"
    assert out["chart_name"] == "revenue-trend"


def test_artifact_builder_returns_none_for_plain_text():
    """Plain text tool results (e.g. sql_explain output) have no artifact."""
    from yigthinker.channels.artifacts import structured_artifact_from_tool_result

    assert structured_artifact_from_tool_result("just a string") is None
    assert structured_artifact_from_tool_result({"message": "ok"}) is None


# ── choose_best_artifact ranking ────────────────────────────────────────────

def test_choose_best_artifact_prefers_file_over_table():
    """A file artifact (artifact_write) outranks a DataFrame preview table."""
    from yigthinker.channels.artifacts import choose_best_artifact

    artifacts = [
        {"kind": "table", "title": "preview", "columns": [], "rows": [], "total_rows": 0},
        {"kind": "file", "filename": "summary.xlsx", "path": "/tmp/summary.xlsx", "bytes": 1},
    ]
    best = choose_best_artifact(artifacts)
    assert best is not None
    assert best["kind"] == "file"


def test_choose_best_artifact_prefers_chart_over_file():
    """A chart outranks a file (per the helper docstring: chart > file > table)."""
    from yigthinker.channels.artifacts import choose_best_artifact

    artifacts = [
        {"kind": "file", "filename": "a.xlsx", "path": "/tmp/a.xlsx", "bytes": 1},
        {"kind": "chart", "chart_name": "c", "chart_json": "{}"},
    ]
    best = choose_best_artifact(artifacts)
    assert best is not None
    assert best["kind"] == "chart"


def test_choose_best_artifact_returns_none_for_empty():
    from yigthinker.channels.artifacts import choose_best_artifact
    assert choose_best_artifact([]) is None


# ── Adapter-level _build_card_for_artifact smoke tests ─────────────────────

def test_teams_build_card_for_file_artifact_includes_filename():
    """Teams _build_card_for_artifact must reference the filename in the card."""
    from yigthinker.channels.teams.adapter import TeamsAdapter

    adapter = TeamsAdapter({
        "tenant_id": "t",
        "client_id": "c",
        "client_secret": "s",
        "webhook_secret": "w",
    })

    card = adapter._build_card_for_artifact(
        "done",
        {
            "kind": "file",
            "filename": "monthly_close.xlsx",
            "path": "/tmp/monthly_close.xlsx",
            "bytes": 1024,
            "summary": "April close",
        },
    )

    # Serialize the card dict and verify the filename is present.
    # We don't assert on exact card shape (Adaptive Card JSON is verbose)
    # but we DO assert the filename is reachable from the card.
    import json
    card_text = json.dumps(card)
    assert "monthly_close.xlsx" in card_text, (
        f"Teams file card must reference filename. Card was: {card_text[:400]}"
    )


def test_feishu_build_card_for_file_artifact_includes_filename():
    """Feishu _build_card_for_artifact must reference the filename in the card."""
    try:
        from yigthinker.channels.feishu.adapter import FeishuAdapter
    except Exception:
        pytest.skip("Feishu adapter import failed; skipping")

    adapter = FeishuAdapter({"app_id": "x", "app_secret": "y", "verification_token": "v"})

    card = adapter._build_card_for_artifact(
        "done",
        {
            "kind": "file",
            "filename": "summary.xlsx",
            "path": "/tmp/summary.xlsx",
            "bytes": 1024,
            "summary": "Summary",
        },
    )

    import json
    card_text = json.dumps(card)
    assert "summary.xlsx" in card_text, (
        f"Feishu file card must reference filename. Card was: {card_text[:400]}"
    )
