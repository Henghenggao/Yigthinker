import json
import pytest
import plotly.express as px
import pandas as pd

from yigthinker.visualization.vchart import plotly_to_vchart
from yigthinker.visualization.exporter import ChartExporter


@pytest.fixture
def bar_chart_json():
    df = pd.DataFrame({"category": ["A", "B", "C"], "value": [10, 20, 15]})
    return px.bar(df, x="category", y="value").to_json()


@pytest.fixture
def line_chart_json():
    df = pd.DataFrame({"date": ["2026-01", "2026-02", "2026-03"], "revenue": [100, 150, 130]})
    return px.line(df, x="date", y="revenue").to_json()


@pytest.fixture
def pie_chart_json():
    df = pd.DataFrame({"segment": ["A", "B", "C"], "share": [40, 35, 25]})
    return px.pie(df, names="segment", values="share").to_json()


def test_bar_chart_translation(bar_chart_json):
    spec = plotly_to_vchart(bar_chart_json)
    assert spec["type"] == "common"
    assert any(s["type"] == "bar" for s in spec["series"])
    assert "data" in spec
    # Values carried through
    values = spec["data"][0]["values"]
    assert len(values) == 3
    assert {"x": "A", "y": 10, "series": values[0]["series"]} == values[0] or values[0]["y"] == 10


def test_line_chart_translation(line_chart_json):
    spec = plotly_to_vchart(line_chart_json)
    assert any(s["type"] == "line" for s in spec["series"])
    assert len(spec["data"][0]["values"]) == 3


def test_pie_chart_translation(pie_chart_json):
    spec = plotly_to_vchart(pie_chart_json)
    assert any(s["type"] == "pie" for s in spec["series"])
    values = spec["data"][0]["values"]
    assert len(values) == 3
    assert "category" in values[0]
    assert "value" in values[0]


def test_unsupported_type_raises_value_error():
    """Unsupported trace types raise ValueError instead of silently producing
    a wrong bar chart. Callers should catch this and fall back to a link card."""
    plotly_json = json.dumps({"data": [{"type": "mesh3d", "x": [1], "y": [2], "z": [3]}], "layout": {}})
    with pytest.raises(ValueError, match="mesh3d"):
        plotly_to_vchart(plotly_json)


def test_empty_traces_returns_stub():
    plotly_json = json.dumps({"data": [], "layout": {}})
    spec = plotly_to_vchart(plotly_json)
    assert spec["type"] == "common"
    assert spec["series"] == []
    assert spec["data"] == [{"values": []}]


def test_title_propagation_dict_form():
    plotly_json = json.dumps({
        "data": [{"type": "bar", "x": ["A"], "y": [1]}],
        "layout": {"title": {"text": "My Dict Title"}},
    })
    spec = plotly_to_vchart(plotly_json)
    assert spec["title"]["text"] == "My Dict Title"


def test_title_propagation_string_form():
    plotly_json = json.dumps({
        "data": [{"type": "bar", "x": ["A"], "y": [1]}],
        "layout": {"title": "My String Title"},
    })
    spec = plotly_to_vchart(plotly_json)
    assert spec["title"]["text"] == "My String Title"


def test_no_title_when_absent():
    plotly_json = json.dumps({
        "data": [{"type": "bar", "x": ["A"], "y": [1]}],
        "layout": {},
    })
    spec = plotly_to_vchart(plotly_json)
    assert "title" not in spec


def test_single_trace_cartesian_has_no_seriesfield():
    plotly_json = json.dumps({
        "data": [{"type": "bar", "x": ["A", "B"], "y": [1, 2], "name": "only"}],
        "layout": {},
    })
    spec = plotly_to_vchart(plotly_json)
    assert spec["series"][0]["seriesField"] is None


def test_multi_trace_cartesian_has_seriesfield():
    plotly_json = json.dumps({
        "data": [
            {"type": "bar", "x": ["A", "B"], "y": [1, 2], "name": "t1"},
            {"type": "bar", "x": ["A", "B"], "y": [3, 4], "name": "t2"},
        ],
        "layout": {},
    })
    spec = plotly_to_vchart(plotly_json)
    assert all(s["seriesField"] == "series" for s in spec["series"])
    # Both series' values merged into same data frame
    assert len(spec["data"][0]["values"]) == 4


def test_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        plotly_to_vchart("not-valid-json")


def test_histogram_maps_to_bar():
    # Histogram uses x only (or y); treat like a cartesian bar chart
    plotly_json = json.dumps({
        "data": [{"type": "histogram", "x": ["A", "B", "C"], "y": [1, 2, 3]}],
        "layout": {},
    })
    spec = plotly_to_vchart(plotly_json)
    assert spec["series"][0]["type"] == "bar"


def test_exporter_to_vchart_roundtrip(bar_chart_json):
    """ChartExporter.to_vchart should return the same spec as direct translation."""
    exporter = ChartExporter()
    spec = exporter.to_vchart(bar_chart_json)
    assert spec["type"] == "common"
    assert any(s["type"] == "bar" for s in spec["series"])
    # Round-trip parity
    assert spec == plotly_to_vchart(bar_chart_json)


def test_exporter_to_vchart_pie(pie_chart_json):
    exporter = ChartExporter()
    spec = exporter.to_vchart(pie_chart_json)
    assert any(s["type"] == "pie" for s in spec["series"])
