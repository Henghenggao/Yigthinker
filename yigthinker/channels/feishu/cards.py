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
