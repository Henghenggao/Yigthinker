"""Microsoft Teams Adaptive Card renderer.

Builds Adaptive Card JSON payloads for Teams channel responses.
"""
from __future__ import annotations

from typing import Any


class TeamsCardRenderer:
    """Renders agent output as Teams Adaptive Card payloads."""

    def render_text(self, text: str) -> dict[str, Any]:
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": [
                {"type": "TextBlock", "text": text, "wrap": True},
            ],
        }

    def render_thinking(self) -> dict[str, Any]:
        return self.render_text("Analyzing...")

    def render_dataframe_summary(
        self,
        name: str,
        shape: tuple[int, int],
        columns: list[str],
        sample_rows: list[list[Any]],
    ) -> dict[str, Any]:
        table_columns = [{"type": "Column", "width": "auto", "items": [
            {"type": "TextBlock", "text": col, "weight": "Bolder"}
        ]} for col in columns]

        rows = []
        for row in sample_rows[:5]:
            row_cols = [{"type": "Column", "width": "auto", "items": [
                {"type": "TextBlock", "text": str(cell)}
            ]} for cell in row]
            rows.append({"type": "ColumnSet", "columns": row_cols})

        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": [
                {"type": "TextBlock", "text": f"{name} ({shape[0]}x{shape[1]})", "weight": "Bolder"},
                {"type": "ColumnSet", "columns": table_columns},
                *rows,
            ],
        }

    def render_chart_link(self, title: str, url: str, description: str = "") -> dict[str, Any]:
        body: list[dict] = [{"type": "TextBlock", "text": title, "weight": "Bolder"}]
        if description:
            body.append({"type": "TextBlock", "text": description, "wrap": True})
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": body,
            "actions": [{"type": "Action.OpenUrl", "title": "Open in Dashboard", "url": url}],
        }

    def render_error(self, message: str) -> dict[str, Any]:
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": [
                {"type": "TextBlock", "text": "Error", "weight": "Bolder", "color": "Attention"},
                {"type": "TextBlock", "text": message, "wrap": True, "fontType": "Monospace"},
            ],
        }
