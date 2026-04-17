from __future__ import annotations

from dataclasses import dataclass

_KNOWN_COMMANDS = frozenset({"new", "switch", "branch", "sessions", "undo"})


@dataclass
class ChannelCommand:
    name: str
    args: list[str]
    raw_text: str


def parse_channel_command(text: str) -> ChannelCommand | None:
    """Parse a /command from message text. Returns None if not a known command."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split(None, 2)  # split into max 3 tokens
    cmd_name = parts[0][1:]  # remove leading /

    if cmd_name not in _KNOWN_COMMANDS:
        return None

    args = parts[1:] if len(parts) > 1 else []
    return ChannelCommand(name=cmd_name, args=args, raw_text=text)
