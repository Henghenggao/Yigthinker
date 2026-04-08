"""Tests for DataFrame copy-in and merge-back between parent and child sessions."""

import pandas as pd
import pytest

from yigthinker.session import VarRegistry
from yigthinker.subagent.dataframes import copy_dataframes_to_child, merge_back_dataframes


# ── copy-in tests ──────────────────────────────────────────────────────────


def test_copy_in_shallow():
    parent = VarRegistry()
    child = VarRegistry()
    df = pd.DataFrame({"a": range(100), "b": range(100), "c": range(100)})
    parent.set("sales", df)

    copy_dataframes_to_child(parent, child, ["sales"])

    child_df = child.get("sales")
    assert child_df.shape == (100, 3)
    # Modify child -- should NOT affect parent (pandas 3.x CoW)
    child_df["a"] = 999
    assert parent.get("sales")["a"].iloc[0] != 999


def test_copy_in_only_specified():
    parent = VarRegistry()
    child = VarRegistry()
    parent.set("sales", pd.DataFrame({"x": [1, 2]}))
    parent.set("inventory", pd.DataFrame({"y": [3, 4]}))

    copy_dataframes_to_child(parent, child, ["sales"])

    assert "sales" in child
    with pytest.raises(KeyError):
        child.get("inventory")


def test_copy_in_missing_name():
    parent = VarRegistry()
    child = VarRegistry()

    with pytest.raises(KeyError):
        copy_dataframes_to_child(parent, child, ["nonexistent"])


def test_copy_in_non_dataframe():
    parent = VarRegistry()
    child = VarRegistry()
    chart = {"type": "bar", "data": [1, 2, 3]}
    parent.set("my_chart", chart, var_type="chart")

    copy_dataframes_to_child(parent, child, ["my_chart"])

    # Non-DataFrame values are copied by reference (no .copy() call)
    assert child.get("my_chart") is chart


# ── merge-back tests ───────────────────────────────────────────────────────


def test_merge_back_prefix():
    parent = VarRegistry()
    child = VarRegistry()
    result_df = pd.DataFrame({"col1": range(50), "col2": range(50)})
    child.set("result_df", result_df)

    merge_back_dataframes(parent, child, "east", set())

    merged = parent.get("east_result_df")
    assert merged.shape == (50, 2)


def test_merge_back_includes_copied_in():
    parent = VarRegistry()
    child = VarRegistry()
    original = pd.DataFrame({"a": [1, 2, 3]})
    parent.set("sales", original)

    copy_dataframes_to_child(parent, child, ["sales"])
    # Modify the child copy
    child_sales = child.get("sales")
    child_sales["a"] = [10, 20, 30]
    child.set("sales", child_sales)

    merge_back_dataframes(parent, child, "east", {"sales"})

    east_sales = parent.get("east_sales")
    assert east_sales["a"].tolist() == [10, 20, 30]


def test_merge_back_summary():
    parent = VarRegistry()
    child = VarRegistry()
    child.set("result_df", pd.DataFrame({"a": range(50), "b": range(50)}))

    summary = merge_back_dataframes(parent, child, "east", set())

    assert "DataFrames merged back:" in summary
    assert "east_result_df: 50x2" in summary


def test_merge_back_empty():
    parent = VarRegistry()
    child = VarRegistry()

    summary = merge_back_dataframes(parent, child, "east", set())

    assert summary == ""


def test_merge_back_preserves_var_type():
    parent = VarRegistry()
    child = VarRegistry()
    child.set("my_chart", {"type": "bar"}, var_type="chart")

    merge_back_dataframes(parent, child, "east", set())

    # Verify the value was merged
    assert parent.get("east_my_chart") == {"type": "bar"}
    # Verify var_type preserved via list() inspection
    infos = parent.list()
    chart_info = [i for i in infos if i.name == "east_my_chart"][0]
    assert chart_info.var_type == "chart"
