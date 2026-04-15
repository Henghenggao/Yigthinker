"""Chart export: Plotly JSON -> PNG, HTML."""
from __future__ import annotations

import json

import plotly.graph_objects as go


def _parse_fig_json(fig_json: str) -> dict:
    """Parse a Plotly figure JSON string, raising ValueError with a helpful message on failure."""
    try:
        return json.loads(fig_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"fig_json is not valid JSON: {exc}. "
            f"Expected output of Plotly fig.to_json() or the chart_json "
            f"stored in ctx.vars by chart_create."
        ) from exc


class ChartExporter:
    """Convert Plotly figures to platform-optimized formats."""

    def to_png(self, fig_json: str, width: int = 1000, height: int = 600) -> bytes:
        """Render Plotly JSON to PNG bytes via kaleido.

        Note: kaleido >= 1.0 depends on Google Chrome being available on the
        system. If Chrome is missing, plotly raises a RuntimeError with
        instructions to run `plotly_get_chrome`. Install via:
            pip install -e .[visualization]
        """
        fig = go.Figure(_parse_fig_json(fig_json))
        return fig.to_image(format="png", width=width, height=height)

    def to_html(self, fig_json: str, cdn: bool = True) -> str:
        """Render Plotly JSON to interactive HTML string.

        Args:
            cdn: If True, reference plotly.js via CDN (~5KB).
                 If False, embed plotly.js inline (~3.5MB).
        """
        fig = go.Figure(_parse_fig_json(fig_json))
        return fig.to_html(
            full_html=True,
            include_plotlyjs="cdn" if cdn else True,
        )
