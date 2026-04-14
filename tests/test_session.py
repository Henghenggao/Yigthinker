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


def test_var_registry_typed_set_and_get():
    reg = VarRegistry()
    reg.set("chart1", '{"data": []}', var_type="chart")
    assert reg.get("chart1") == '{"data": []}'


def test_var_registry_list_includes_all_types():
    reg = VarRegistry()
    df = pd.DataFrame({"a": [1]})
    reg.set("my_df", df)
    reg.set("my_chart", '{"data": []}', var_type="chart")
    infos = reg.list()
    assert len(infos) == 2
    names = {i.name for i in infos}
    assert names == {"my_df", "my_chart"}


def test_var_info_dataframe_has_type():
    reg = VarRegistry()
    df = pd.DataFrame({"x": [1], "y": [2]})
    reg.set("df1", df)
    info = reg.list()[0]
    assert info.var_type == "dataframe"
    assert info.shape == (1, 2)
    assert "x" in info.dtypes


def test_var_info_chart_has_type():
    reg = VarRegistry()
    reg.set("c1", '{"data": []}', var_type="chart")
    info = reg.list()[0]
    assert info.var_type == "chart"
    assert info.shape == (0, 0)


def test_var_registry_default_type_is_dataframe():
    reg = VarRegistry()
    df = pd.DataFrame({"a": [1]})
    reg.set("df1", df)
    infos = reg.list()
    assert infos[0].var_type == "dataframe"


def test_session_context_has_context_manager():
    from yigthinker.context_manager import ContextManager
    ctx = SessionContext()
    assert isinstance(ctx.context_manager, ContextManager)


def test_session_context_independent_context_managers():
    s1 = SessionContext()
    s2 = SessionContext()
    assert s1.context_manager is not s2.context_manager


async def test_emit_progress_calls_callback():
    ctx = SessionContext()
    calls = []
    ctx._progress_callback = lambda msg: calls.append(msg)
    await ctx.emit_progress("loading data")
    assert calls == ["loading data"]


async def test_emit_progress_noop_without_callback():
    ctx = SessionContext()
    # Should not raise
    await ctx.emit_progress("nothing happens")
