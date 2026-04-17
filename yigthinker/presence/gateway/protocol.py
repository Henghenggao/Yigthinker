"""WebSocket message protocol for Gateway ↔ TUI communication.

All messages are JSON-serialized dicts with a ``type`` discriminator.
``request_id`` is optional and used for client-side correlation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ── Client → Server ─────────────────────────────────────────────────────────

@dataclass
class AuthMsg:
    token: str
    type: str = "auth"


@dataclass
class AttachMsg:
    session_key: str
    type: str = "attach"


@dataclass
class DetachMsg:
    session_key: str
    type: str = "detach"


@dataclass
class UserInputMsg:
    text: str
    request_id: str = ""
    type: str = "user_input"


@dataclass
class SlashCmdMsg:
    command: str
    args: str = ""
    request_id: str = ""
    type: str = "slash_cmd"


# ── Server → Client ─────────────────────────────────────────────────────────

@dataclass
class AuthResultMsg:
    ok: bool
    message: str = ""
    type: str = "auth_result"


@dataclass
class TokenStreamMsg:
    text: str
    type: str = "token"


@dataclass
class ToolCallMsg:
    tool_name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_id: str = ""
    type: str = "tool_call"


@dataclass
class ToolResultMsg:
    tool_id: str
    content: str
    is_error: bool = False
    type: str = "tool_result"


@dataclass
class ResponseDoneMsg:
    full_text: str
    request_id: str = ""
    type: str = "response_done"


@dataclass
class VarsUpdateMsg:
    vars: list[dict[str, Any]] = field(default_factory=list)
    type: str = "vars_update"


@dataclass
class SessionListMsg:
    sessions: list[dict[str, Any]] = field(default_factory=list)
    type: str = "session_list"


@dataclass
class ErrorMsg:
    message: str
    request_id: str = ""
    type: str = "error"


@dataclass
class SubagentEventMsg:
    """Lifecycle event for subagent status changes (SPAWN-18, D-17)."""
    subagent_id: str
    subagent_name: str
    event: str  # "spawned" | "completed" | "failed" | "cancelled"
    detail: str = ""
    type: str = "subagent_event"


@dataclass
class ToolProgressMsg:
    """In-flight progress message from a tool execution."""
    tool: str
    message: str
    type: str = "tool_progress"


# ── Helpers ──────────────────────────────────────────────────────────────────

def to_json_dict(msg: Any) -> dict[str, Any]:
    """Convert a protocol dataclass to a plain dict for JSON serialization."""
    return asdict(msg)


_CLIENT_MSG_TYPES: dict[str, type] = {
    "auth": AuthMsg,
    "attach": AttachMsg,
    "detach": DetachMsg,
    "user_input": UserInputMsg,
    "slash_cmd": SlashCmdMsg,
}


def parse_client_msg(data: dict[str, Any]) -> Any:
    """Parse a raw JSON dict into the appropriate client message dataclass.

    Raises ``ValueError`` if the message type is unknown.
    """
    msg_type = data.get("type", "")
    cls = _CLIENT_MSG_TYPES.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown client message type: {msg_type!r}")
    # Only pass known fields to the dataclass constructor
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)
