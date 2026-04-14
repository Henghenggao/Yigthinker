# tests/test_permissions.py
import pytest
from yigthinker.permissions import PermissionSystem

@pytest.fixture
def perms():
    return PermissionSystem({
        "allow": ["schema_inspect", "chart_create"],
        "ask": ["sql_query", "df_transform"],
        "deny": ["sql_query(DELETE:*)", "sql_query(DROP:*)"],
    })

def test_allow_rule_matches(perms):
    assert perms.check("schema_inspect") == "allow"
    assert perms.check("chart_create") == "allow"

def test_ask_rule_matches(perms):
    assert perms.check("df_transform") == "ask"

def test_deny_takes_priority_over_ask(perms):
    assert perms.check("sql_query", {"query": "DELETE FROM orders"}) == "deny"

def test_drop_is_denied(perms):
    assert perms.check("sql_query", {"query": "DROP TABLE users"}) == "deny"

def test_select_falls_through_to_ask(perms):
    assert perms.check("sql_query", {"query": "SELECT * FROM orders"}) == "ask"

def test_unknown_tool_defaults_to_ask(perms):
    assert perms.check("unknown_tool") == "ask"

def test_empty_permissions_defaults_to_ask():
    p = PermissionSystem({})
    assert p.check("any_tool") == "ask"


def test_session_scoped_override_grants_access():
    p = PermissionSystem({"ask": ["df_transform"]})
    p.allow_for_session("df_transform", "session-1")
    assert p.check("df_transform", session_id="session-1") == "allow"


def test_session_scoped_override_isolated():
    p = PermissionSystem({"ask": ["df_transform"]})
    p.allow_for_session("df_transform", "session-1")
    # Different session should NOT be affected
    assert p.check("df_transform", session_id="session-2") == "ask"


def test_session_scoped_override_no_session_id():
    p = PermissionSystem({"ask": ["df_transform"]})
    p.allow_for_session("df_transform", "session-1")
    # Without session_id, override is not visible
    assert p.check("df_transform") == "ask"


def test_clear_session_removes_overrides():
    p = PermissionSystem({"ask": ["df_transform"]})
    p.allow_for_session("df_transform", "session-1")
    p.clear_session("session-1")
    assert p.check("df_transform", session_id="session-1") == "ask"


def test_deny_still_overrides_session_allow():
    p = PermissionSystem({"deny": ["sql_query(DELETE:*)"], "ask": ["sql_query"]})
    p.allow_for_session("sql_query", "session-1")
    # Deny always wins
    assert p.check("sql_query", {"query": "DELETE FROM t"}, session_id="session-1") == "deny"


# -- bypassAll mode --

def test_bypass_all_allows_everything():
    p = PermissionSystem({}, mode="bypassAll")
    assert p.check("sql_query", {"query": "DELETE FROM t"}) == "allow"
    assert p.check("df_transform") == "allow"
    assert p.check("workflow_deploy") == "allow"


def test_bypass_all_respects_explicit_deny():
    """bypassAll should NOT override explicit deny rules — deny rules are absolute."""
    p = PermissionSystem({"deny": ["sql_query(DELETE:*)"]}, mode="bypassAll")
    assert p.check("sql_query", {"query": "DELETE FROM t"}) == "deny"


# -- denyAll mode --

def test_deny_all_blocks_everything():
    p = PermissionSystem({}, mode="denyAll")
    assert p.check("schema_inspect") == "deny"
    assert p.check("df_load") == "deny"


# -- acceptEdits mode --

def test_accept_edits_auto_allows_edit_tools():
    p = PermissionSystem({}, mode="acceptEdits")
    for tool in ("df_transform", "df_merge", "df_load", "chart_create", "chart_modify",
                 "report_generate", "forecast_timeseries", "forecast_regression"):
        assert p.check(tool) == "allow", f"{tool} should be auto-allowed in acceptEdits mode"


def test_accept_edits_still_asks_for_sql_dml():
    p = PermissionSystem({}, mode="acceptEdits")
    assert p.check("sql_query", {"query": "DELETE FROM t"}) == "ask"


def test_accept_edits_still_asks_for_workflow_deploy():
    p = PermissionSystem({}, mode="acceptEdits")
    assert p.check("workflow_deploy") == "ask"


# -- default mode unchanged --

def test_default_mode_behaves_as_before():
    p = PermissionSystem({"allow": ["schema_inspect"], "deny": ["sql_query(DELETE:*)"]})
    assert p.check("schema_inspect") == "allow"
    assert p.check("sql_query", {"query": "DELETE FROM t"}) == "deny"
    assert p.check("unknown") == "ask"
