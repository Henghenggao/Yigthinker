from __future__ import annotations

from typing import Any
from yigthinker.presence.tui._import_error import TEXTUAL_IMPORT_ERROR

try:
    from textual.widgets import Static
except ImportError as exc:
    raise ImportError(TEXTUAL_IMPORT_ERROR) from exc


class VarsPanel(Static):
    def update_vars(self, vars_list: list[dict[str, Any]]) -> None:
        if not vars_list:
            self.update("[dim]No variables[/]")
            return

        lines = ["[bold]ctx.vars[/]\n"]
        for item in vars_list:
            name = item.get("name", "?")
            shape = item.get("shape", ())
            dtypes = item.get("dtypes", {})
            width = f"{shape[0]}x{shape[1]}" if len(shape) >= 2 else "?"
            cols = ", ".join(list(dtypes)[:3])
            suffix = f"  [{cols}]" if cols else ""
            lines.append(f"  [cyan]{name}[/]  ({width}){suffix}")

        self.update("\n".join(lines))
