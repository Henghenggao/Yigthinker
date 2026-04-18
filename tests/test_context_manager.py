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


# ---------------------------------------------------------------------------
# 2026-04-18 UAT finding: LLM doesn't know configured connection names,
# defaults to "default" which isn't in the pool → wastes a tool_call.
# Fix: inject available-connections directive into system prompt.
# ---------------------------------------------------------------------------

def test_build_connections_directive_lists_names(cm):
    """When connections are configured, directive must list each name + type
    so the LLM can pick the right one without a failed probe call."""
    settings = {
        "connections": {
            "sample": {"type": "sqlite", "path": "/tmp/s.db"},
            "prod_dw": {"type": "postgresql", "host": "db.example.com"},
        },
    }
    directive = cm.build_connections_directive(settings)
    assert directive is not None
    assert "sample" in directive
    assert "prod_dw" in directive
    assert "sqlite" in directive
    assert "postgresql" in directive
    # Directive must tell the LLM HOW to use this — naming the connection
    # parameter on sql_query / schema_inspect is the whole point.
    assert "connection" in directive.lower()


def test_build_connections_directive_none_when_no_connections(cm):
    """No configured connections → no directive (keep system prompt clean).
    Agent will still work against file-based inputs via df_load."""
    assert cm.build_connections_directive({}) is None
    assert cm.build_connections_directive({"connections": {}}) is None


def test_build_connections_directive_never_leaks_passwords(cm):
    """Directive must NEVER include password / credential fields even if
    they were accidentally written into settings.json in plain text.
    We list names + types only."""
    settings = {
        "connections": {
            "risky": {
                "type": "postgresql",
                "host": "db",
                "user": "admin",
                "password": "PLAIN_TEXT_SHOULD_NOT_LEAK",
            },
        },
    }
    directive = cm.build_connections_directive(settings)
    assert directive is not None
    assert "PLAIN_TEXT_SHOULD_NOT_LEAK" not in directive
    assert "password" not in directive.lower()


def test_build_connections_directive_single_connection_sets_default(cm):
    """If there's exactly one connection, it should be highlighted as the
    obvious default — reducing LLM choice paralysis on the first call."""
    settings = {
        "connections": {"only_one": {"type": "sqlite", "path": "/x.db"}},
    }
    directive = cm.build_connections_directive(settings)
    assert directive is not None
    assert "only_one" in directive
    # Should indicate this is the single/default connection to use
    assert any(hint in directive.lower()
               for hint in ("only", "single", "default", "use `only_one`"))
