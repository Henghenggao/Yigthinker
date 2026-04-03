from __future__ import annotations

from typing import Any

try:
    from textual.widgets import Static
except ImportError as exc:
    raise ImportError(
        "TUI requires the 'textual' package. Install with: pip install yigthinker[tui]"
    ) from exc


class ToolCard(Static):
    """Collapsible tool call display widget -- mounted into chat-panel Vertical container."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        collapsed: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_input = tool_input or {}
        self._result_content: str = ""
        self._is_error: bool = False
        self._collapsed = collapsed
        self._has_result = False

    def on_mount(self) -> None:
        self._render()

    def set_result(self, content: str, is_error: bool = False) -> None:
        self._result_content = content
        self._is_error = is_error
        self._has_result = True
        self._render()

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._render()

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    @collapsed.setter
    def collapsed(self, value: bool) -> None:
        self._collapsed = value
        self._render()

    def _render(self) -> None:
        if self._collapsed:
            status = "[dim]running...[/]" if not self._has_result else (
                "[red]error[/]" if self._is_error else "[green]done[/]"
            )
            self.update(f"  [bold dim]> {self._tool_name}[/]  {status}")
        else:
            lines: list[str] = [f"  [bold]> {self._tool_name}[/]"]
            if self._tool_input:
                params = ", ".join(
                    f"{k}={v!r}" for k, v in list(self._tool_input.items())[:5]
                )
                lines.append(f"    Input: {params}")
            if self._has_result:
                style = "red" if self._is_error else "green"
                truncated = self._result_content[:300]
                if len(self._result_content) > 300:
                    truncated += "..."
                lines.append(f"    [{style}]Result: {truncated}[/]")
            else:
                lines.append("    [dim]Running...[/]")
            self.update("\n".join(lines))
