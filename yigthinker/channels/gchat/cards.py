"""Google Chat Cards v2 renderer."""
from __future__ import annotations

from typing import Any


class GChatCardRenderer:
    """Renders agent output as Google Chat Cards v2 payloads."""

    def render_text(self, text: str) -> dict[str, Any]:
        return {
            "cardsV2": [{
                "cardId": "result",
                "card": {
                    "sections": [{
                        "widgets": [{"textParagraph": {"text": text}}],
                    }],
                },
            }],
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
        header = " | ".join(columns)
        rows = "\n".join(" | ".join(str(c) for c in row) for row in sample_rows[:5])
        text = f"<b>{name}</b> ({shape[0]} rows x {shape[1]} cols)\n\n{header}\n{rows}"
        return self.render_text(text)

    def render_chart_link(self, title: str, url: str, description: str = "") -> dict[str, Any]:
        widgets: list[dict] = []
        if description:
            widgets.append({"textParagraph": {"text": description}})
        widgets.append({
            "buttonList": {"buttons": [{
                "text": "Open chart",
                "onClick": {"openLink": {"url": url}},
            }]},
        })
        return {
            "cardsV2": [{
                "cardId": "chart",
                "card": {
                    "header": {"title": title},
                    "sections": [{"widgets": widgets}],
                },
            }],
        }

    def render_error(self, message: str) -> dict[str, Any]:
        return {
            "cardsV2": [{
                "cardId": "error",
                "card": {
                    "header": {"title": "Error", "subtitle": "Yigthinker"},
                    "sections": [{
                        "widgets": [{"textParagraph": {"text": f"<pre>{message}</pre>"}}],
                    }],
                },
            }],
        }
