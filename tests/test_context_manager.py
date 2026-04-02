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
