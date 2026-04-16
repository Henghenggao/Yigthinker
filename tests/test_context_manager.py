# tests/test_context_manager.py
import pandas as pd
import pytest
from yigthinker.context_manager import ContextManager


@pytest.fixture
def cm():
    return ContextManager(max_tokens=100_000)


def test_small_dataframe_returned_as_records(cm):
    df = pd.DataFrame({"a": range(5), "b": range(5)})
    result = cm.summarize_dataframe_result(df)
    assert result["type"] == "dataframe"
    assert len(result["data"]) == 5


def test_large_dataframe_summarized(cm):
    df = pd.DataFrame({"value": range(50_000)})
    result = cm.summarize_dataframe_result(df)
    assert result["type"] == "dataframe_summary"
    assert result["total_rows"] == 50_000
    assert len(result["sample"]) == 10
    assert "stats" in result
    assert "note" in result


def test_boundary_at_10_rows(cm):
    df_10 = pd.DataFrame({"x": range(10)})
    df_11 = pd.DataFrame({"x": range(11)})
    assert cm.summarize_dataframe_result(df_10)["type"] == "dataframe"
    assert cm.summarize_dataframe_result(df_11)["type"] == "dataframe_summary"


# ---------------------------------------------------------------------------
# Phase 10 / BHV-01: automation awareness directive
# ---------------------------------------------------------------------------

def test_build_automation_directive_enabled(cm):
    """D-23 + D-24: returns the locked directive text when behavior.suggest_automation.enabled=True."""
    settings = {
        "behavior": {"suggest_automation": {"enabled": True}},
    }
    directive = cm.build_automation_directive(settings)
    assert directive is not None
    assert isinstance(directive, str)
    # Locked D-23 text -- the exact wording is CONTEXT-locked and must appear verbatim.
    assert "Automation awareness" in directive
    assert "suggest_automation" in directive
    assert "workflow_generate" in directive
    assert "one-off or exploratory" in directive.lower()
    # quick-260416-j3y: the directive must explicitly route one-off scripts and
    # custom-formatted outputs away from workflow_generate toward artifact_write.
    assert "artifact_write" in directive
    assert "custom-formatted" in directive


def test_build_automation_directive_disabled(cm):
    """D-24: returns None when the feature flag is disabled so system_prompt stays clean."""
    settings_off = {
        "behavior": {"suggest_automation": {"enabled": False}},
    }
    assert cm.build_automation_directive(settings_off) is None

    # Also: missing settings block altogether -> default is ENABLED (D-24 says default=True)
    settings_missing: dict = {}
    directive_default = cm.build_automation_directive(settings_missing)
    assert directive_default is not None
    assert "Automation awareness" in directive_default
