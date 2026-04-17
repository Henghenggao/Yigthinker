"""Feishu interactive card renderer.

Builds Feishu CardV2 JSON payloads for DataFrame summaries, chart links,
thinking placeholders, and error messages.

Feishu card spec: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message-card
"""
from __future__ import annotations

from typing import Any


class FeishuCardRenderer:
    """Renders agent output as Feishu interactive card JSON payloads."""

    def render_text(self, text: str) -> dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {"tag": "markdown", "content": text},
            ],
        }

    def render_thinking(self) -> dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Yigthinker"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": "Analyzing..."},
            ],
        }

    def render_dataframe_summary(
        self,
        name: str,
        shape: tuple[int, int],
        columns: list[str],
        sample_rows: list[list[Any]],
    ) -> dict[str, Any]:
        # Build markdown table
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        rows = "\n".join(
            "| " + " | ".join(str(cell) for cell in row) + " |"
            for row in sample_rows[:5]
        )
        table_md = f"**{name}** ({shape[0]} rows x {shape[1]} cols)\n\n{header}\n{separator}\n{rows}"

        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {"tag": "markdown", "content": table_md},
            ],
        }

    def render_chart_link(self, title: str, url: str, description: str = "") -> dict[str, Any]:
        elements: list[dict[str, Any]] = []
        if description:
            elements.append({"tag": "markdown", "content": description})
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "Open chart"},
                "url": url,
                "type": "primary",
            }],
        })
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "green",
            },
            "elements": elements,
        }

    def render_chart_image(
        self,
        chart_name: str,
        image_key: str,
        interactive_url: str | None = None,
    ) -> dict[str, Any]:
        """Feishu card with uploaded chart image."""
        elements: list[dict[str, Any]] = [
            {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": chart_name}},
        ]
        if interactive_url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "Open Interactive"},
                    "type": "primary",
                    "url": interactive_url,
                }],
            })
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": chart_name}, "template": "blue"},
            "elements": elements,
        }

    def render_file_saved(
        self,
        filename: str,
        size_bytes: int,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """Feishu card announcing an artifact_write / report_generate file result.

        Shown when the agent persists a file artifact (Excel/PDF/script). We keep
        the card simple — no download action, because the workspace path is local
        to the gateway host. Parallels TeamsCardRenderer.render_file_saved.
        """
        elements: list[dict[str, Any]] = [
            {"tag": "markdown", "content": f"**Saved {filename}**"},
            {"tag": "markdown", "content": f"Saved to workspace · {size_bytes:,} B"},
        ]
        if summary:
            elements.append({"tag": "markdown", "content": summary})
        return {
            "config": {"wide_screen_mode": True},
            "elements": elements,
        }

    def render_vchart_native(self, chart_name: str, vchart_spec: dict[str, Any]) -> dict[str, Any]:
        """Feishu-exclusive: native interactive chart via VChart in card."""
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": chart_name}, "template": "blue"},
            "elements": [
                {"tag": "chart", "chart_spec": {"type": "vchart", "data": vchart_spec}, "height": "380px"},
            ],
        }

    def render_native_table(
        self,
        title: str,
        columns: list[str],
        rows: list[list[str]],
        total_rows: int,
    ) -> dict[str, Any]:
        """Feishu card with native table element."""
        table_columns = [{"name": col, "display_name": col} for col in columns]
        table_rows = [dict(zip(columns, row)) for row in rows]
        elements: list[dict[str, Any]] = [
            {"tag": "table", "page_size": min(len(rows), 10), "columns": table_columns, "rows": table_rows},
        ]
        if total_rows > len(rows):
            elements.append({
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"Showing {len(rows)} of {total_rows} rows"}],
            })
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
            "elements": elements,
        }

    def render_error(self, message: str) -> dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Error"},
                "template": "red",
            },
            "elements": [
                {"tag": "markdown", "content": f"```\n{message}\n```"},
            ],
        }
