"""Chart export: Plotly JSON -> PNG, HTML."""
from __future__ import annotations

import json

import plotly.graph_objects as go


class ChartExporter:
    """Convert Plotly figures to platform-optimized formats."""

    def to_png(self, fig_json: str, width: int = 1000, height: int = 600) -> bytes:
        """Render Plotly JSON to PNG bytes via kaleido."""
        fig = go.Figure(json.loads(fig_json))
        return fig.to_image(format="png", width=width, height=height)

    def to_html(self, fig_json: str, cdn: bool = True) -> str:
        """Render Plotly JSON to interactive HTML string.

        Args:
            cdn: If True, reference plotly.js via CDN (~5KB).
                 If False, embed plotly.js inline (~3.5MB).
        """
        fig = go.Figure(json.loads(fig_json))
        return fig.to_html(
            full_html=True,
            include_plotlyjs="cdn" if cdn else True,
        )
