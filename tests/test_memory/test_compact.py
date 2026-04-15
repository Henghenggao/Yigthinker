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


async def test_no_compact_below_threshold():
    compact = SmartCompact(CompactConfig(max_tokens=100000))
    messages = _make_messages(4)
    result, injection = await compact.run(messages, memory_content="", token_estimate=1000)
    assert result == messages  # unchanged
    assert injection == ""


async def test_compacts_when_over_threshold():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result, injection = await compact.run(messages, memory_content="## Project Memory\nSome facts.", token_estimate=50000)
    assert len(result) < len(messages)
    # Memory is now injected via system prompt, not as a user message
    assert injection != ""
    assert "[Session Memory" in injection


async def test_memory_injected_via_system_prompt():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result, injection = await compact.run(messages, memory_content="Key fact: revenue is 1M.", token_estimate=50000)
    # Memory goes into system injection, not a user message prepended to result
    assert "[Session Memory" in injection
    # No consecutive user messages at the start of the compacted list
    if len(result) >= 2:
        assert not (result[0].role == "user" and result[1].role == "user")


async def test_vars_summary_appended_to_injection():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result, injection = await compact.run(
        messages,
        memory_content="Key fact.",
        token_estimate=50000,
        vars_summary="sales: 1000×5",
    )
    assert "[DataFrame Variables]" in injection
    assert "sales: 1000×5" in injection


async def test_fallback_truncation_when_memory_empty():
    compact = SmartCompact(CompactConfig(max_tokens=100, min_tokens=0, min_text_block_messages=0))
    messages = _make_messages(10)
    result, injection = await compact.run(messages, memory_content="", token_estimate=50000)
    # Falls back to generic truncation (keeps recent messages)
    assert len(result) < len(messages)
    assert injection == ""
