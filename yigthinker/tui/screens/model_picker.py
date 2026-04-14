from __future__ import annotations

from yigthinker.tui._import_error import TEXTUAL_IMPORT_ERROR

try:
    from textual.app import ComposeResult
    from textual.screen import ModalScreen
    from textual.widgets import OptionList, Static
    from textual.widgets.option_list import Option
except ImportError as exc:
    raise ImportError(TEXTUAL_IMPORT_ERROR) from exc


_DEFAULT_MODELS: list[str] = [
    "claude-sonnet-4-20250514",
    "gpt-4o",
    "o4-mini",
    "ollama/llama3",
]


class ModelPickerScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss_picker", "Close")]

    def __init__(self, models: list[str] | None = None) -> None:
        super().__init__()
        self._models = models if models is not None else list(_DEFAULT_MODELS)

    def compose(self) -> ComposeResult:
        yield Static("[bold]Switch Model[/] (Enter to select, Escape to cancel)")
        if not self._models:
            yield Static("[dim]No models available[/]")
        else:
            options = [Option(m, id=m) for m in self._models]
            yield OptionList(*options, id="model-list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    def action_dismiss_picker(self) -> None:
        self.dismiss(None)
