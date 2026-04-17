"""CardRenderer protocol for platform-specific rich output formatting.

Each messaging platform (Feishu, Teams, Google Chat) has its own card/message
format.  The CardRenderer protocol provides a uniform interface for converting
agent output into platform-native rich content.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CardRenderer(Protocol):
    """Render agent output as platform-specific card payloads."""

    def render_text(self, text: str) -> dict[str, Any]:
        """Render a markdown/text response as a card."""
        ...

    def render_thinking(self) -> dict[str, Any]:
        """Render a 'thinking...' placeholder card (for async update pattern)."""
        ...

    def render_dataframe_summary(
        self,
        name: str,
        shape: tuple[int, int],
        columns: list[str],
        sample_rows: list[list[Any]],
    ) -> dict[str, Any]:
        """Render a DataFrame summary as a table card."""
        ...

    def render_chart_link(self, title: str, url: str, description: str = "") -> dict[str, Any]:
        """Render a card linking to a chart or external visualization."""
        ...

    def render_error(self, message: str) -> dict[str, Any]:
        """Render an error message card."""
        ...
