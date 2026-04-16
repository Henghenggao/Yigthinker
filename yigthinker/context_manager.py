from __future__ import annotations
import re
from typing import Any
import pandas as pd

_SAMPLE_ROWS = 10  # rows to include in summarized result

# Patterns that look like prompt injection attempts in memory content.
# These get stripped before memory enters the system prompt.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(prior|previous|above)\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(your\s+)?(prior|previous|above)?\s*(instructions?|rules?)", re.IGNORECASE),
    re.compile(r"forget\s+(your|all|previous)\s+(instructions?|rules?|training)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+(system\s+)?directive:", re.IGNORECASE),
    re.compile(r"system\s+override:", re.IGNORECASE),
    re.compile(r"always\s+execute\s+.{0,30}without\s+permission", re.IGNORECASE),
    re.compile(r"bypass\s+(all\s+)?(permission|security|safety)", re.IGNORECASE),
]


def _sanitize_memory_content(content: str) -> str:
    """Remove lines containing prompt injection patterns from memory content.

    Strips suspicious instruction-like patterns that could manipulate LLM
    behavior when injected into the system prompt. Logs stripped lines
    for audit purposes.
    """
    lines = content.split("\n")
    clean_lines: list[str] = []
    stripped_count = 0
    for line in lines:
        if any(pat.search(line) for pat in _INJECTION_PATTERNS):
            stripped_count += 1
            continue
        clean_lines.append(line)
    if stripped_count > 0:
        clean_lines.append(
            f"\n[{stripped_count} suspicious instruction(s) stripped from memory by security filter]"
        )
    return "\n".join(clean_lines)


class ContextManager:
    """Token budget tracking and large result summarization.

    Token budget fractions (from spec):
        system prompt   20%
        data context    30%  (schemas + samples injected by tools)
        session history 40%
        reserve buffer  10%
    """

    SYSTEM_FRACTION = 0.20
    DATA_CONTEXT_FRACTION = 0.30
    HISTORY_FRACTION = 0.40
    RESERVE_FRACTION = 0.10

    def __init__(self, max_tokens: int = 200_000) -> None:
        self._max_tokens = max_tokens

    @property
    def history_budget(self) -> int:
        return int(self._max_tokens * self.HISTORY_FRACTION)

    @property
    def system_budget(self) -> int:
        """Token budget for system prompt content."""
        return int(self._max_tokens * self.SYSTEM_FRACTION)

    def build_memory_section(self, memory_content: str) -> str:
        """Format loaded memory for system prompt injection.

        Memory shares the 20% system prompt allocation.
        Truncate if memory exceeds half the system budget (~20K tokens).
        Content is sanitized to strip prompt injection patterns before
        entering the system prompt.
        """
        if not memory_content or not memory_content.strip():
            return ""

        # Sanitize: strip lines that look like prompt injection attempts
        content = _sanitize_memory_content(memory_content)

        max_memory_tokens = int(self._max_tokens * self.SYSTEM_FRACTION * 0.5)
        max_memory_chars = max_memory_tokens * 4  # rough reverse estimate

        if len(content) > max_memory_chars:
            content = content[:max_memory_chars] + "\n\n[Memory truncated -- run /compact to consolidate]"

        return f"\n\n--- Accumulated Knowledge (factual summaries only) ---\n{content}\n--- End Knowledge ---\n"

    def build_automation_directive(self, settings: dict[str, Any]) -> str | None:
        """Return the BHV-01 automation awareness directive for the system prompt.

        D-23: the directive text is locked exactly as written in CONTEXT.md -- this
        method is a pure renderer that reads the D-24 gate and returns either the
        full directive string or None.

        D-24: controlled by `settings['behavior']['suggest_automation']['enabled']`.
        Default is True when the key is missing, so users on old settings.json files
        still get the directive without explicit opt-in.
        """
        behavior_cfg = settings.get("behavior", {}) if settings else {}
        suggest_cfg = behavior_cfg.get("suggest_automation", {})
        enabled = suggest_cfg.get("enabled", True)
        if not enabled:
            return None

        # D-23 locked text -- do NOT paraphrase.
        # quick-260416-j3y appends one clause at the end to explicitly steer the
        # LLM away from forcing one-off scripts / custom Excel outputs through
        # workflow_generate (the root cause of a Teams agent-loop timeout
        # documented in .planning/quick/260416-j3y-*).
        return (
            "**Automation awareness**: When the user completes a data analysis "
            "task, briefly consider whether the work is likely to repeat (daily "
            "reports, monthly closes, recurring investigations). If so, call "
            "`suggest_automation` to see detected patterns and offer to generate "
            "a workflow via `workflow_generate`. Do not suggest automation for "
            "one-off or exploratory analyses. "
            "Do not push one-off scripts, ad-hoc reports, or custom-formatted "
            "outputs (e.g. openpyxl-styled Excel) through `workflow_generate` — "
            "those belong in `artifact_write` or a direct reply."
        )

    def build_narration_directive(self, settings: dict[str, Any]) -> str | None:
        """Return the chat-narration directive for the system prompt.

        Instructs the agent to narrate tool usage in natural language so that
        IM channels (Teams / Feishu / GChat) don't need to render raw tool
        JSON — the agent's own reply carries the progress story.

        Gated by ``settings['behavior']['narrate_tool_usage']['enabled']``.
        Default is True so fresh settings.json files get the behavior.
        """
        behavior_cfg = settings.get("behavior", {}) if settings else {}
        narrate_cfg = behavior_cfg.get("narrate_tool_usage", {})
        enabled = narrate_cfg.get("enabled", True)
        if not enabled:
            return None

        return (
            "**Tool usage narration**: When you call tools, weave a brief "
            "natural-language progress note into your reply so the user "
            "understands what you did and why. Reply in the user's "
            "conversation language. Describe outcomes and next steps in "
            "plain prose — do NOT paste raw tool JSON, argument blobs, or "
            "schema-like structures into the chat. One short sentence per "
            "tool call is usually enough (e.g. \"已读取 Excel，共 4 个 "
            "sheet\" rather than \"df_load returned {\\\"sheets\\\": [...]}\")."
        )

    def summarize_dataframe_result(self, df: pd.DataFrame) -> dict[str, Any]:
        """Return full records for small DataFrames; summary for large ones.

        Threshold: > 10 rows triggers summarization. Full data stays in the
        VarRegistry, not in the message history.
        """
        if len(df) <= _SAMPLE_ROWS:
            return {"type": "dataframe", "data": df.to_dict(orient="records")}

        return {
            "type": "dataframe_summary",
            "total_rows": len(df),
            "columns": list(df.columns),
            "sample": df.head(_SAMPLE_ROWS).to_dict(orient="records"),
            "stats": df.describe(include="all").to_dict(),
            "note": (
                f"Full dataset ({len(df):,} rows) stored in variable registry. "
                f"Showing first {_SAMPLE_ROWS} rows + statistical summary."
            ),
        }
