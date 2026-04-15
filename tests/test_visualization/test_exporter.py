import json
import pytest
import plotly.express as px
import pandas as pd

from yigthinker.visualization.exporter import ChartExporter


@pytest.fixture
def sample_chart_json():
    df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "revenue": [100, 150, 130]})
    fig = px.bar(df, x="month", y="revenue")
    return fig.to_json()


@pytest.fixture
def exporter():
    return ChartExporter()


def test_to_png_returns_bytes(exporter, sample_chart_json):
    result = exporter.to_png(sample_chart_json)
    assert isinstance(result, bytes)
    assert len(result) > 1000
    assert result[:8] == b"\x89PNG\r\n\x1a\n"


def test_to_png_custom_dimensions(exporter, sample_chart_json):
    small = exporter.to_png(sample_chart_json, width=200, height=150)
    large = exporter.to_png(sample_chart_json, width=2000, height=1500)
    assert len(large) > len(small)


def test_to_html_returns_string(exporter, sample_chart_json):
    result = exporter.to_html(sample_chart_json)
    assert isinstance(result, str)
    assert "<html>" in result.lower() or "plotly" in result.lower()
    assert "cdn.plot.ly" in result


def test_to_html_self_contained(exporter, sample_chart_json):
    result = exporter.to_html(sample_chart_json, cdn=False)
    # No external <script src="..."> tags — plotly.js is fully inlined.
    # (The string "cdn.plot.ly" may appear inside the bundled JS as a config
    # default for topojson tiles; that is fine and expected.)
    assert 'src="https://cdn.plot.ly' not in result
    assert len(result) > 100_000  # plotly.js embedded
