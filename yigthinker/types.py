from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Literal


@dataclass
class ToolResult:
    tool_use_id: str
    content: Any
    is_error: bool = False


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


class HookAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class HookResult:
    """
    Usage:
        HookResult.ALLOW                   # singleton, no parentheses
        HookResult.warn("message")         # classmethod
        HookResult.block("reason")         # classmethod
    """

    ALLOW: ClassVar["HookResult"]  # set after class definition

    def __init__(self, action: HookAction, message: str = "") -> None:
        self.action = action
        self.message = message

    @classmethod
    def warn(cls, message: str) -> "HookResult":
        return cls(HookAction.WARN, message)

    @classmethod
    def block(cls, message: str) -> "HookResult":
        return cls(HookAction.BLOCK, message)

    def __repr__(self) -> str:
        return f"HookResult({self.action.value!r}, {self.message!r})"


HookResult.ALLOW = HookResult(HookAction.ALLOW)


@dataclass
class HookEvent:
    event_type: Literal[
        "PreToolUse", "PostToolUse", "UserPromptSubmit",
        "Stop", "SessionStart", "SessionEnd", "PreCompact"
    ]
    session_id: str
    transcript_path: str
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_result: ToolResult | None = None
    user_prompt: str = ""


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: Any  # str | list[dict]


@dataclass
class LLMResponse:
    stop_reason: Literal["tool_use", "end_turn", "max_tokens"]
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
