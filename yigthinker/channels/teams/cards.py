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
            "actions": [{"type": "Action.OpenUrl", "title": "Open chart", "url": url}],
        }

    def render_file_received(self, filenames: list[str]) -> dict[str, Any]:
        """Render a card acknowledging received file attachments."""
        count = len(filenames)
        header = f"Received {count} file{'s' if count != 1 else ''}"
        items: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": header, "weight": "Bolder"},
        ]
        for name in filenames:
            items.append(
                {"type": "TextBlock", "text": f"- {name}", "wrap": True}
            )
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": items,
        }

    def render_tool_progress(self, tool_name: str, summary: str) -> dict[str, Any]:
        """Render a compact progress card showing a tool result summary."""
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": [
                {
                    "type": "ColumnSet",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [{"type": "TextBlock", "text": tool_name, "weight": "Bolder", "size": "Small"}],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [{"type": "TextBlock", "text": summary, "wrap": True, "size": "Small"}],
                        },
                    ],
                },
            ],
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
