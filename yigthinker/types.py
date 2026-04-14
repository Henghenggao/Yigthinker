from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Literal


@dataclass
class ToolResult:
    tool_use_id: str
    content: Any
    is_error: bool = False
    _suppressed: bool = field(default=False, repr=False)
    _hook_injections: list[str] = field(default_factory=list, repr=False)


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


class HookAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    INJECT_SYSTEM = "inject_system"
    SUPPRESS_OUTPUT = "suppress_output"
    REPLACE_RESULT = "replace_result"


class HookResult:
    """
    Usage:
        HookResult.ALLOW                        # singleton, no parentheses
        HookResult.warn("message")              # classmethod
        HookResult.block("reason")              # classmethod
        HookResult.inject_system("text")        # classmethod — P1-5
        HookResult.suppress()                   # classmethod — P1-5
        HookResult.replace(content)             # classmethod — P1-5
    """

    ALLOW: ClassVar["HookResult"]  # set after class definition

    def __init__(self, action: HookAction, message: str = "") -> None:
        self.action = action
        self.message = message
        self.replacement: Any = None

    @classmethod
    def warn(cls, message: str) -> "HookResult":
        return cls(HookAction.WARN, message)

    @classmethod
    def block(cls, message: str) -> "HookResult":
        return cls(HookAction.BLOCK, message)

    @classmethod
    def inject_system(cls, text: str) -> "HookResult":
        """Inject text into LLM system prompt for the next call."""
        return cls(HookAction.INJECT_SYSTEM, text)

    @classmethod
    def suppress(cls) -> "HookResult":
        """Suppress tool result — LLM does not see it."""
        return cls(HookAction.SUPPRESS_OUTPUT)

    @classmethod
    def replace(cls, content: Any) -> "HookResult":
        """Replace tool result content with provided value."""
        r = cls(HookAction.REPLACE_RESULT)
        r.replacement = content
        return r

    def __repr__(self) -> str:
        return f"HookResult({self.action.value!r}, {self.message!r})"


HookResult.ALLOW = HookResult(HookAction.ALLOW)


@dataclass
class HookAggregateResult:
    """Aggregated result from running all matching hooks."""

    action: HookAction = HookAction.ALLOW
    message: str = ""
    injections: list[str] = field(default_factory=list)
    suppress: bool = False
    replacement: Any = None


@dataclass
class HookEvent:
    event_type: Literal[
        "PreToolUse", "PostToolUse", "UserPromptSubmit",
        "Stop", "SessionStart", "SessionEnd", "PreCompact",
        "SubagentStop",
    ]
    session_id: str
    transcript_path: str
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_result: ToolResult | None = None
    user_prompt: str = ""
    subagent_id: str = ""
    subagent_name: str = ""
    subagent_status: str = ""  # "completed" | "failed" | "cancelled"
    subagent_final_text: str = ""  # truncated summary per D-14


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: Any  # str | list[dict]


@dataclass
class ThinkingConfig:
    enabled: bool = False
    budget_tokens: int = 10000


@dataclass
class LLMResponse:
    stop_reason: Literal["tool_use", "end_turn", "max_tokens"]
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    thinking_blocks: list[dict] = field(default_factory=list)


@dataclass
class StreamEvent:
    type: Literal["text", "tool_use", "done", "error"]
    text: str = ""
    tool_use: ToolUse | None = None
    stop_reason: str = ""
    error: str = ""
