from __future__ import annotations
from dataclasses import dataclass
from yigthinker.types import Message


@dataclass
class CompactConfig:
    min_tokens: int = 10000          # reserved: minimum token count before compaction is eligible
    max_tokens: int = 40000
    min_text_block_messages: int = 5


class SmartCompact:
    def __init__(self, config: CompactConfig | None = None) -> None:
        self._cfg = config or CompactConfig()

    async def run(
        self,
        messages: list[Message],
        memory_content: str,
        token_estimate: int,
        vars_summary: str = "",
    ) -> tuple[list[Message], str]:
        """
        Run smart compact. Returns (compacted_messages, system_injection).

        system_injection is non-empty when memory should be prepended to the
        system prompt for the next LLM call. Injecting memory via the system
        prompt rather than as a role="user" message prevents consecutive
        user-role messages, which the Anthropic API rejects with HTTP 400.

        If token_estimate < max_tokens, returns (messages, "").
        If memory_content is empty, falls back to generic tail truncation.
        """
        if token_estimate < self._cfg.max_tokens:
            return messages, ""

        # Determine how many recent messages to keep
        keep = max(self._cfg.min_text_block_messages, len(messages) // 3)
        recent = messages[-keep:]

        if not memory_content.strip():
            return recent, ""

        # Build memory injection for system prompt (avoids consecutive user messages)
        memory_parts = ["[Session Memory — auto-extracted]\n", memory_content]
        if vars_summary:
            memory_parts.append(f"\n\n[DataFrame Variables]\n{vars_summary}")

        return recent, "".join(memory_parts)
