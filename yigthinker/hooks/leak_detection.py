"""PostToolUse hook: scan tool results for credential leaks and redact before LLM context."""
from __future__ import annotations

import os
import re
from yigthinker.types import HookEvent, HookResult

# Environment variable keys that commonly hold secrets.
_SECRET_ENV_KEYS = frozenset({
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT", "DATABASE_URL", "GATEWAY_TOKEN",
})

# Regex patterns for well-known token formats.
_TOKEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"), "ANTHROPIC_KEY"),
    (re.compile(r"sk-[a-zA-Z0-9\-]{20,}"), "API_KEY"),
    (re.compile(r"xoxb-[0-9]{10,}-[a-zA-Z0-9]+"), "SLACK_TOKEN"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GITHUB_TOKEN"),
    (re.compile(r"vault://[^\s]+"), "VAULT_REF"),
]

_MIN_SECRET_LENGTH = 8


class LeakDetector:
    """Discover secrets from environment and scan text for leaks."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}
        for key in _SECRET_ENV_KEYS:
            val = os.environ.get(key, "")
            if len(val) >= _MIN_SECRET_LENGTH:
                self._secrets[key] = val

    def scan(self, content: str) -> tuple[str, list[str]]:
        """Return (redacted_content, list_of_detection_names)."""
        detections: list[str] = []

        # 1. Exact value matching — longest first to prevent partial replacement.
        for name, value in sorted(self._secrets.items(), key=lambda x: -len(x[1])):
            if value in content:
                content = content.replace(value, f"[REDACTED:{name}]")
                detections.append(name)

        # 2. Regex pattern matching for dynamic tokens.
        for pattern, label in _TOKEN_PATTERNS:
            if pattern.search(content):
                content = pattern.sub(f"[REDACTED:{label}]", content)
                detections.append(label)

        return content, detections


# Module-level singleton, initialized on first import.
_detector: LeakDetector | None = None


def _get_detector() -> LeakDetector:
    global _detector
    if _detector is None:
        _detector = LeakDetector()
    return _detector


async def leak_detection_hook(event: HookEvent) -> HookResult:
    """PostToolUse hook: redact credentials from tool results."""
    if event.tool_result is None or event.tool_result.is_error:
        return HookResult.ALLOW

    content_str = str(event.tool_result.content)
    redacted, detections = _get_detector().scan(content_str)

    if detections:
        return HookResult.replace(redacted)

    return HookResult.ALLOW
