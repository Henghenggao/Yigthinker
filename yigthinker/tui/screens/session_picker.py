from __future__ import annotations

from typing import Any

try:
    from textual.app import ComposeResult
    from textual.screen import ModalScreen
    from textual.widgets import OptionList, Static
    from textual.widgets.option_list import Option
except ImportError as exc:
    raise ImportError(
        "TUI requires the 'textual' package. Install with: pip install yigthinker[tui]"
    ) from exc


def _format_idle(seconds: float) -> str:
    """Convert idle_seconds to a human-readable relative timestamp."""
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        m = int(seconds // 60)
        return f"{m}m ago"
    elif seconds < 86400:
        h = int(seconds // 3600)
        return f"{h}h ago"
    else:
        d = int(seconds // 86400)
        return f"{d}d ago"


class SessionPickerScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss_picker", "Close")]

    def __init__(self, sessions: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._sessions = sessions or []

    def compose(self) -> ComposeResult:
        yield Static("[bold]Switch Session[/] (Enter to select, Escape to cancel)")
        if not self._sessions:
            yield Static("[dim]No active sessions[/]")
        else:
            options: list[Option] = []
            for s in self._sessions:
                key = s.get("key", "unknown")
                msg_count = s.get("message_count", 0)
                var_count = s.get("var_count", 0)
                idle = s.get("idle_seconds", 0)
                timestamp = _format_idle(idle)
                label = f"{key}  |  {timestamp}  |  {msg_count} msgs  |  {var_count} vars"
                options.append(Option(label, id=key))
            yield OptionList(*options, id="session-list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    def action_dismiss_picker(self) -> None:
        self.dismiss(None)
