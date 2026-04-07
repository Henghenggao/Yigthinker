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
