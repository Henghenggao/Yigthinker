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

    def render_chart_image(
        self,
        chart_name: str,
        png_url: str,
        interactive_url: str | None = None,
    ) -> dict[str, Any]:
        """Adaptive Card with inline chart PNG and optional interactive link."""
        body: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": chart_name, "weight": "Bolder", "size": "Medium"},
            {"type": "Image", "url": png_url, "size": "Stretch", "altText": chart_name},
        ]
        actions: list[dict[str, Any]] = []
        if interactive_url:
            actions.append(
                {"type": "Action.OpenUrl", "title": "Open Interactive", "url": interactive_url}
            )
        card: dict[str, Any] = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": body,
        }
        if actions:
            card["actions"] = actions
        return card

    def render_native_table(
        self,
        title: str,
        columns: list[str],
        rows: list[list[Any]],
        total_rows: int,
    ) -> dict[str, Any]:
        """Adaptive Card with native Table element (v1.5+)."""
        table_columns = [{"width": 1} for _ in columns]
        header_cells = [
            {"type": "TableCell", "items": [{"type": "TextBlock", "text": c, "weight": "Bolder"}]}
            for c in columns
        ]
        table_rows: list[dict[str, Any]] = [
            {"type": "TableRow", "cells": header_cells, "style": "accent"}
        ]
        for row in rows:
            table_rows.append(
                {
                    "type": "TableRow",
                    "cells": [
                        {
                            "type": "TableCell",
                            "items": [{"type": "TextBlock", "text": str(v), "wrap": True}],
                        }
                        for v in row
                    ],
                }
            )
        body: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium"},
            {"type": "Table", "columns": table_columns, "rows": table_rows},
        ]
        if total_rows > len(rows):
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"Showing {len(rows)} of {total_rows} rows",
                    "size": "Small",
                    "isSubtle": True,
                }
            )
        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": body,
        }

    def render_file_saved(
        self,
        filename: str,
        size_bytes: int,
        summary: str | None = None,
        download_url: str | None = None,
    ) -> dict[str, Any]:
        """Adaptive Card announcing an artifact_write / excel_write result.

        When ``download_url`` is provided (quick-260416-kyn: Teams signed-URL
        delivery for binary artifacts), append an Action.OpenUrl button that
        the Teams client opens in the user's browser. When omitted, the card
        stays path-only — same shape as the original artifact_write UX, so
        text artifacts (.py/.md/.sql) never surface a download link.
        """
        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"Saved {filename}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"Saved to workspace \u00b7 {size_bytes:,} B",
                "size": "Small",
                "isSubtle": True,
                "wrap": True,
            },
        ]
        if summary:
            body.append({"type": "TextBlock", "text": summary, "wrap": True})
        card: dict[str, Any] = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": body,
        }
        if download_url:
            card["actions"] = [
                {
                    "type": "Action.OpenUrl",
                    "title": f"Download {filename}",
                    "url": download_url,
                }
            ]
        return card

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
