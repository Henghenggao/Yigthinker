import pytest
from yigthinker.memory.compact import SmartCompact, CompactConfig
from yigthinker.types import Message


def _make_messages(n: int) -> list[Message]:
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append(Message(role=role, content=f"message {i}"))
    return msgs


def test_compact_config_defaults():
    cfg = CompactConfig()
    assert cfg.min_tokens == 10000
    assert cfg.max_tokens == 40000
    assert cfg.min_text_block_messages == 5


def test_no_compact_below_threshold():
    compact = SmartCompact(CompactConfig(max_tokens=100000))
    messages = _make_messages(4)
    result = compact.run(messages, memory_content="", token_estimate=1000)
    assert result == messages  # unchanged


def test_compacts_when_over_threshold():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result = compact.run(messages, memory_content="## Project Memory\nSome facts.", token_estimate=50000)
    assert len(result) < len(messages)
    assert "[Session Memory" in result[0].content  # memory injection happened


def test_memory_injected_as_first_message():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result = compact.run(messages, memory_content="Key fact: revenue is 1M.", token_estimate=50000)
    assert "[Session Memory" in result[0].content


def test_vars_summary_appended_to_memory_message():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result = compact.run(
        messages,
        memory_content="Key fact.",
        token_estimate=50000,
        vars_summary="sales: 1000×5",
    )
    assert "[DataFrame Variables]" in result[0].content
    assert "sales: 1000×5" in result[0].content


def test_fallback_truncation_when_memory_empty():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result = compact.run(messages, memory_content="", token_estimate=50000)
    # Falls back to generic truncation (keeps recent messages)
    assert len(result) < len(messages)
