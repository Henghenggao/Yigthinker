from __future__ import annotations

try:
    from textual.widgets import Static
except ImportError as exc:
    raise ImportError(
        "TUI requires the 'textual' package. Install with: pip install yigthinker[tui]"
    ) from exc


class StatusBar(Static):
    def set_status(
        self,
        session: str = "",
        model: str = "",
        state: str = "disconnected",
    ) -> None:
        colors = {
            "connected": "green",
            "connecting": "yellow",
            "reconnecting": "yellow",
            "disconnected": "red",
            "auth_failed": "red",
        }
        color = colors.get(state, "red")
        parts = []
        if session:
            parts.append(f"Session: {session}")
        if model:
            parts.append(f"Model: {model}")
        parts.append(f"[{color}]{state}[/]")
        self.update("  |  ".join(parts))
