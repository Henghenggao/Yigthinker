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
