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

    def run(
        self,
        messages: list[Message],
        memory_content: str,
        token_estimate: int,
        vars_summary: str = "",
    ) -> list[Message]:
        """
        Run smart compact. Returns compacted message list.
        If token_estimate < max_tokens, returns messages unchanged.
        If memory_content is empty, falls back to generic tail truncation.
        """
        if token_estimate < self._cfg.max_tokens:
            return messages

        # Determine how many recent messages to keep
        keep = max(self._cfg.min_text_block_messages, len(messages) // 3)
        recent = messages[-keep:]

        if not memory_content.strip():
            # Generic fallback: just keep recent tail
            return recent

        # Smart compact: inject memory summary as first message
        memory_msg_parts = ["[Session Memory — auto-extracted]\n", memory_content]
        if vars_summary:
            memory_msg_parts.append(f"\n\n[DataFrame Variables]\n{vars_summary}")

        memory_message = Message(
            role="user",
            content="".join(memory_msg_parts),
        )
        return [memory_message] + recent
