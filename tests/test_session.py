# tests/test_session.py
import pandas as pd
import pytest
from yigthinker.session import SessionContext, VarRegistry

def test_var_registry_set_and_get():
    reg = VarRegistry()
    df = pd.DataFrame({"a": [1, 2, 3]})
    reg.set("df1", df)
    result = reg.get("df1")
    assert list(result.columns) == ["a"]
    assert len(result) == 3

def test_var_registry_list():
    reg = VarRegistry()
    df = pd.DataFrame({"x": [1], "y": [2]})
    reg.set("my_df", df)
    info = reg.list()
    assert len(info) == 1
    assert info[0].name == "my_df"
    assert info[0].shape == (1, 2)
    assert "x" in info[0].dtypes

def test_var_registry_get_missing_raises():
    reg = VarRegistry()
    with pytest.raises(KeyError, match="df99"):
        reg.get("df99")

def test_var_registry_contains():
    reg = VarRegistry()
    reg.set("df1", pd.DataFrame())
    assert "df1" in reg
    assert "df2" not in reg

def test_session_context_has_unique_id():
    s1 = SessionContext()
    s2 = SessionContext()
    assert s1.session_id != s2.session_id

def test_session_context_vars_independent():
    s1 = SessionContext()
    s2 = SessionContext()
    s1.vars.set("df1", pd.DataFrame({"a": [1]}))
    assert "df1" not in s2.vars
