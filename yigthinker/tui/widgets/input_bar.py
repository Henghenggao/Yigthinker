from __future__ import annotations

from typing import Sequence

try:
    from textual.suggester import Suggester
    from textual.widgets import Input
except ImportError as exc:
    raise ImportError(
        "TUI requires the 'textual' package. Install with: pip install yigthinker[tui]"
    ) from exc


_DEFAULT_COMMANDS: list[str] = [
    "/help", "/clear", "/model", "/session", "/vars", "/export", "/quit",
]


class SlashCommandSuggester(Suggester):
    """Only suggest when input starts with /"""

    def __init__(self, commands: Sequence[str] | None = None) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._commands: list[str] = list(commands) if commands else list(_DEFAULT_COMMANDS)

    async def get_suggestion(self, value: str) -> str | None:
        if not value.startswith("/"):
            return None
        prefix = value.lower()
        for cmd in self._commands:
            if cmd.lower().startswith(prefix) and cmd.lower() != prefix:
                return cmd
        return None


class InputBar(Input):
    class Submitted(Input.Submitted):
        pass

    def __init__(self, commands: Sequence[str] | None = None) -> None:
        super().__init__(
            id="input-bar",
            placeholder="Type a message... (Enter to send, / for commands)",
            suggester=SlashCommandSuggester(commands),
        )
