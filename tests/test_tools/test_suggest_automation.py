"""Tests for SuggestAutomationTool (Phase 10 BHV-03 / BHV-04): read-only workflow
tool that lists detected automation opportunities from PatternStore.

These tests were written BEFORE the implementation lands (Wave 0 / RED phase).
They will only pass once `yigthinker/tools/workflow/suggest_automation.py` is
created in Task 2.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from yigthinker.session import SessionContext


def _make_ctx() -> SessionContext:
    """Minimal SessionContext — SuggestAutomationTool does not read ctx.vars."""
    # SessionContext uses default_factory for all fields, so a zero-arg construction
    # is sufficient. The tool never reads model/provider — it only needs the dataclass
    # shape to satisfy the YigthinkerTool protocol signature.
    return SessionContext()


def _make_pattern_dict(
    pattern_id: str,
    frequency: int = 3,
    estimated_time_saved_minutes: int = 20,
    suppressed: bool = False,
    suppressed_until: str | None = None,
) -> dict:
    return {
        "pattern_id": pattern_id,
        "description": f"Description for {pattern_id}",
        "tool_sequence": ["sql_query", "df_transform", "chart_create"],
        "frequency": frequency,
        "estimated_time_saved_minutes": estimated_time_saved_minutes,
        "required_connections": ["sqlite"],
        "first_seen": "2026-04-01T10:00:00+00:00",
        "last_seen": "2026-04-10T14:30:00+00:00",
        "sessions": ["session-a", "session-b"],
        "suppressed": suppressed,
        "suppressed_until": suppressed_until,
    }


@pytest.fixture
def real_store(tmp_path: Path):
    """Provide a real PatternStore seeded via its own save() method."""
    from yigthinker.memory.patterns import PatternStore

    return PatternStore(path=tmp_path / "patterns.json")


async def test_output_shape(real_store) -> None:
    """BHV-03: execute() returns {suggestions: [...], summary: str} with every required field
    per suggestion, sorted by time_saved * frequency descending."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    real_store.save({
        "patterns": {
            "small_win": _make_pattern_dict("small_win", frequency=3, estimated_time_saved_minutes=5),
            "big_win": _make_pattern_dict("big_win", frequency=10, estimated_time_saved_minutes=30),
            "mid_win": _make_pattern_dict("mid_win", frequency=5, estimated_time_saved_minutes=15),
        }
    })

    tool = SuggestAutomationTool(store=real_store)
    result = await tool.execute(SuggestAutomationInput(), _make_ctx())

    assert result.is_error is False
    content = result.content
    assert isinstance(content, dict)
    assert "suggestions" in content
    assert "summary" in content
    assert isinstance(content["summary"], str)

    suggestions = content["suggestions"]
    assert len(suggestions) == 3

    # Sort check: big_win (10*30=300) > mid_win (5*15=75) > small_win (3*5=15)
    ids_in_order = [s["pattern_id"] for s in suggestions]
    assert ids_in_order == ["big_win", "mid_win", "small_win"]

    # Each suggestion must carry every required field.
    required_fields = {
        "pattern_id", "description", "tool_sequence", "frequency",
        "estimated_time_saved_minutes", "required_connections", "last_seen",
        "can_deploy_to",
    }
    for s in suggestions:
        assert required_fields.issubset(s.keys()), (
            f"Missing keys in suggestion: {required_fields - s.keys()}"
        )
        assert isinstance(s["can_deploy_to"], list)
        assert "local" in s["can_deploy_to"]  # local is always available


async def test_filter_min_frequency(real_store) -> None:
    """BHV-03: min_frequency filters out patterns with frequency below the threshold."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    real_store.save({
        "patterns": {
            "rare": _make_pattern_dict("rare", frequency=1),
            "common": _make_pattern_dict("common", frequency=5),
            "borderline": _make_pattern_dict("borderline", frequency=2),
        }
    })
    tool = SuggestAutomationTool(store=real_store)

    # Default min_frequency=2 includes borderline + common, excludes rare
    result_default = await tool.execute(SuggestAutomationInput(), _make_ctx())
    ids_default = {s["pattern_id"] for s in result_default.content["suggestions"]}
    assert ids_default == {"borderline", "common"}

    # min_frequency=3 only includes common
    result_strict = await tool.execute(SuggestAutomationInput(min_frequency=3), _make_ctx())
    ids_strict = {s["pattern_id"] for s in result_strict.content["suggestions"]}
    assert ids_strict == {"common"}


async def test_can_deploy_to_via_findspec(real_store) -> None:
    """D-21: can_deploy_to is computed via `importlib.util.find_spec` — never via import.

    We verify this by patching `importlib.util.find_spec` and asserting it is called with
    the expected module names. NO real import of `yigthinker_mcp_powerautomate` or
    `yigthinker_mcp_uipath` must occur (they do not exist in the test environment)."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    real_store.save({
        "patterns": {
            "one": _make_pattern_dict("one", frequency=3),
        }
    })
    tool = SuggestAutomationTool(store=real_store)

    calls: list[str] = []

    def fake_find_spec(name: str):
        calls.append(name)
        # Simulate: power_automate is available, uipath is not.
        if name == "yigthinker_mcp_powerautomate":
            return object()  # any truthy non-None value
        return None

    with patch(
        "yigthinker.tools.workflow.suggest_automation.importlib.util.find_spec",
        side_effect=fake_find_spec,
    ):
        result = await tool.execute(SuggestAutomationInput(), _make_ctx())

    # find_spec must have been called for both MCP package names.
    assert "yigthinker_mcp_powerautomate" in calls
    assert "yigthinker_mcp_uipath" in calls

    suggestion = result.content["suggestions"][0]
    assert "local" in suggestion["can_deploy_to"]
    assert "power_automate" in suggestion["can_deploy_to"]
    assert "uipath" not in suggestion["can_deploy_to"]


async def test_dismiss_writes_suppressed_until(real_store) -> None:
    """BHV-04 / D-22: execute(dismiss='<pid>') short-circuits — calls store.suppress(pid, days=90)
    and returns {dismissed, ok} without listing suggestions."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    real_store.save({
        "patterns": {
            "unwanted": _make_pattern_dict("unwanted", frequency=5),
        }
    })
    tool = SuggestAutomationTool(store=real_store)

    result = await tool.execute(
        SuggestAutomationInput(dismiss="unwanted"),
        _make_ctx(),
    )
    assert result.is_error is False
    assert result.content == {"dismissed": "unwanted", "ok": True}

    # patterns.json must now have suppressed=True + suppressed_until in the future
    reloaded = real_store.load()
    entry = reloaded["patterns"]["unwanted"]
    assert entry["suppressed"] is True
    assert entry["suppressed_until"] is not None
    until = datetime.fromisoformat(entry["suppressed_until"])
    assert until > datetime.now(timezone.utc) + timedelta(days=89)


async def test_dismiss_missing_pattern_returns_ok_false(real_store) -> None:
    """Dismissing a non-existent pattern returns {dismissed, ok: False}."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    real_store.save({"patterns": {}})
    tool = SuggestAutomationTool(store=real_store)

    result = await tool.execute(
        SuggestAutomationInput(dismiss="nonexistent"),
        _make_ctx(),
    )
    assert result.is_error is False
    assert result.content == {"dismissed": "nonexistent", "ok": False}


async def test_filter_suppressed_default(real_store) -> None:
    """BHV-04: default include_suppressed=False hides suppressed entries."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    real_store.save({
        "patterns": {
            "visible": _make_pattern_dict("visible", frequency=3),
            "hidden": _make_pattern_dict("hidden", frequency=3, suppressed=True, suppressed_until=future),
        }
    })
    tool = SuggestAutomationTool(store=real_store)

    result = await tool.execute(SuggestAutomationInput(), _make_ctx())
    ids = {s["pattern_id"] for s in result.content["suggestions"]}
    assert ids == {"visible"}


async def test_include_suppressed_true(real_store) -> None:
    """BHV-04: include_suppressed=True returns suppressed entries too."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    real_store.save({
        "patterns": {
            "visible": _make_pattern_dict("visible", frequency=3),
            "hidden": _make_pattern_dict("hidden", frequency=3, suppressed=True, suppressed_until=future),
        }
    })
    tool = SuggestAutomationTool(store=real_store)

    result = await tool.execute(SuggestAutomationInput(include_suppressed=True), _make_ctx())
    ids = {s["pattern_id"] for s in result.content["suggestions"]}
    assert ids == {"visible", "hidden"}


async def test_empty_store_returns_empty_suggestions(real_store) -> None:
    """Missing patterns.json → execute returns empty suggestions with a friendly summary."""
    from yigthinker.tools.workflow.suggest_automation import (
        SuggestAutomationInput,
        SuggestAutomationTool,
    )

    tool = SuggestAutomationTool(store=real_store)
    result = await tool.execute(SuggestAutomationInput(), _make_ctx())
    assert result.is_error is False
    assert result.content["suggestions"] == []
    assert "no automation opportunities" in result.content["summary"].lower()
