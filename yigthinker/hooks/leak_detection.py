"""PostToolUse hook: scan tool results for credential leaks and redact before LLM context."""
from __future__ import annotations

import os
import re
from yigthinker.types import HookEvent, HookResult

# Environment variable keys that commonly hold secrets.
# AZURE_OPENAI_ENDPOINT is intentionally excluded — it is a URL, not a credential,
# and redacting it would silently hide useful debugging information.
_SECRET_ENV_KEYS = frozenset({
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
    "DATABASE_URL", "GATEWAY_TOKEN",
})

# Regex patterns for well-known token formats.
# The broad `sk-[a-zA-Z0-9\-]{20,}` pattern was replaced with targeted sub-patterns
# to avoid false positives on Stripe keys (sk-live_*, sk-test_*) which legitimately
# appear in payment data processed by financial analysis tools.
_TOKEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"), "ANTHROPIC_KEY"),
    (re.compile(r"sk-proj-[a-zA-Z0-9\-_]{20,}"), "OPENAI_PROJECT_KEY"),
    (re.compile(r"sk-svcacct-[a-zA-Z0-9\-_]{20,}"), "OPENAI_SERVICE_KEY"),
    (re.compile(r"sk-[A-Za-z0-9]{48,}"), "OPENAI_CLASSIC_KEY"),  # legacy 51-char sk-... keys
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
    """Return the module singleton.

    Asyncio's single-threaded event loop guarantees no two coroutines can
    interleave inside this function (no await point between the None-check
    and the assignment), so no lock is needed.
    """
    global _detector
    if _detector is None:
        _detector = LeakDetector()
    return _detector


async def leak_detection_hook(event: HookEvent) -> HookResult:
    """PostToolUse hook: redact credentials from tool results.

    Skips error results — credential leaks in error messages (e.g. a
    failed DB connection echoing DATABASE_URL) will NOT be redacted.
    Tradeoff: error diagnostics stay intact; callers must avoid putting
    secrets in error paths.
    """
    if event.tool_result is None or event.tool_result.is_error:
        return HookResult.ALLOW

    content_str = str(event.tool_result.content)
    redacted, detections = _get_detector().scan(content_str)

    if detections:
        return HookResult.replace(redacted)

    return HookResult.ALLOW
