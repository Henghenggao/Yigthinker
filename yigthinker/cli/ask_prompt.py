from __future__ import annotations
from enum import Enum
import asyncio
import json
from rich.console import Console
from rich.panel import Panel

_console = Console()


class PermissionAnswer(Enum):
    ALLOW = "allow"
    ALLOW_ALL = "allow_all"
    DENY = "deny"


def _prompt_user(prompt: str) -> str:
    """Synchronous Rich prompt — patched in tests."""
    return _console.input(prompt).strip().lower()


async def ask_user_permission(tool_name: str, tool_input: dict) -> PermissionAnswer:
    """Show tool call details and ask user to allow/deny."""
    input_preview = json.dumps(tool_input, ensure_ascii=False, indent=2)[:300]
    _console.print(Panel(
        f"[bold yellow]Tool:[/] {tool_name}\n[bold yellow]Input:[/]\n{input_preview}",
        title="[bold red]Permission Required[/]",
        border_style="yellow",
    ))
    raw = await asyncio.get_event_loop().run_in_executor(
        None,
        _prompt_user,
        "[bold]Allow? ([green]y[/]=yes, [red]n[/]=no, [cyan]a[/]=always)[/] ",
    )
    if raw in ("y", "yes"):
        return PermissionAnswer.ALLOW
    if raw in ("a", "always"):
        return PermissionAnswer.ALLOW_ALL
    return PermissionAnswer.DENY
