from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text
from yigthinker.presence.tui._import_error import TEXTUAL_IMPORT_ERROR

try:
    from textual.widgets import RichLog
except ImportError as exc:
    raise ImportError(TEXTUAL_IMPORT_ERROR) from exc


class ChatLog(RichLog):
    def append_user(self, text: str) -> None:
        label = Text("> You: ", style="bold cyan")
        label.append(text)
        self.write(label)

    def append_response(self, text: str) -> None:
        self.write(Text("Assistant:", style="bold green"))
        self.write(Markdown(text))

    def append_tool_call(self, name: str, tool_input: dict | None = None) -> None:
        summary = f"  [tool] {name}"
        if tool_input:
            summary += f"({', '.join(f'{k}={v!r}' for k, v in list(tool_input.items())[:3])})"
        self.write(Text(summary, style="dim"))

    def append_tool_result(self, content: str, is_error: bool = False) -> None:
        style = "red" if is_error else "green"
        truncated = content[:200] + "..." if len(content) > 200 else content
        self.write(Text(f"  => {truncated}", style=style))

    def append_error(self, message: str) -> None:
        self.write(Text(f"Error: {message}", style="bold red"))
