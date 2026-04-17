from __future__ import annotations

from typing import Any
from yigthinker.presence.tui._import_error import TEXTUAL_IMPORT_ERROR

try:
    from textual.app import ComposeResult
    from textual.screen import ModalScreen
    from textual.widgets import RichLog, Static
except ImportError as exc:
    raise ImportError(TEXTUAL_IMPORT_ERROR) from exc

from rich.table import Table


class DataFramePreviewScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss_preview", "Close")]

    def __init__(self, name: str, data: list[dict[str, Any]]) -> None:
        super().__init__()
        self._name = name
        self._data = data  # First 20 rows as list of dicts

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]Preview: {self._name}[/] (first 20 rows, Escape to close)")
        yield RichLog(id="preview-log", highlight=True)

    def on_mount(self) -> None:
        if not self._data:
            self.query_one("#preview-log", RichLog).write("[dim]No data[/]")
            return
        table = Table(title=self._name, show_lines=True)
        for col in self._data[0].keys():
            table.add_column(str(col), overflow="ellipsis", max_width=30)
        for row in self._data[:20]:
            table.add_row(*(str(v) for v in row.values()))
        self.query_one("#preview-log", RichLog).write(table)

    def action_dismiss_preview(self) -> None:
        self.dismiss(None)
