import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from yigthinker.memory.session_memory import MemoryManager, MEMORY_TEMPLATE
from yigthinker.types import Message, LLMResponse


def test_memory_template_has_sections():
    assert "Data Source Knowledge" in MEMORY_TEMPLATE
    assert "Business Rules" in MEMORY_TEMPLATE
    assert "Errors & Corrections" in MEMORY_TEMPLATE
    assert "Key Findings" in MEMORY_TEMPLATE
    assert "Analysis Log" in MEMORY_TEMPLATE


def test_should_extract_every_n_turns():
    mgr = MemoryManager(extract_frequency=5)
    # Should NOT extract at turns 1-4
    for _ in range(4):
        mgr.record_turn()
    assert not mgr.should_extract()
    # 5th turn should trigger
    mgr.record_turn()
    assert mgr.should_extract()


def test_should_not_extract_if_already_running():
    mgr = MemoryManager(extract_frequency=5)
    for _ in range(5):
        mgr.record_turn()
    mgr.start_extraction()
    assert not mgr.should_extract()


def test_memory_path_for_project(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.memory_path()
    assert ".yigthinker" in str(path)
    assert "MEMORY.md" in str(path)


def test_ensure_memory_file_creates_template(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    assert path.exists()
    content = path.read_text()
    assert "Data Source Knowledge" in content


def test_is_template_only(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Fresh file = template only, no actual content
    assert mgr.is_template_only(path)


def test_load_memory_empty_when_template_only(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    mgr.ensure_memory_file()
    # Template-only file should not contribute to loaded memory
    result = mgr.load_memory()
    assert result == ""


def test_load_memory_includes_real_content(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Append real content
    path.write_text(
        "# Data Source Knowledge\norders table has 2M rows. Primary key is order_id.\n",
        encoding="utf-8"
    )
    result = mgr.load_memory()
    assert "orders table" in result
    assert "## Project Memory" in result


async def test_extract_memories_calls_llm(tmp_path):
    """extract_memories sends conversation turns to LLM and writes findings to MEMORY.md."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="# Key Findings\nRevenue grew 15% YoY",
    )
    messages = [Message(role="user", content="Show me revenue trends")]
    result = await mgr.extract_memories(messages, provider)
    provider.chat.assert_called_once()
    path = mgr.ensure_memory_file()
    content = path.read_text(encoding="utf-8")
    assert "Revenue grew 15%" in content


async def test_extraction_sets_running_flag(tmp_path):
    """_extraction_running flag is True during execution and False after."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    flags_during: list[bool] = []

    async def capture_flag(messages, tools, **kwargs):
        flags_during.append(mgr._extraction_running)
        return LLMResponse(stop_reason="end_turn", text="")

    provider = AsyncMock()
    provider.chat.side_effect = capture_flag
    messages = [Message(role="user", content="test")]
    await mgr.extract_memories(messages, provider)
    assert flags_during[0] is True
    assert mgr._extraction_running is False


async def test_extraction_skips_when_llm_returns_empty(tmp_path):
    """If LLM returns empty text, memory file stays template-only."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    mgr.ensure_memory_file()
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="")
    messages = [Message(role="user", content="test")]
    result = await mgr.extract_memories(messages, provider)
    assert result is None
    assert mgr.is_template_only(mgr.memory_path())


async def test_extraction_appends_not_overwrites(tmp_path):
    """New findings are appended under existing section content, not overwriting."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Pre-populate with real content
    content = path.read_text(encoding="utf-8")
    content = content.replace(
        "# Key Findings\n_Important analytical conclusions from this project. Referenced by finding ID for traceability._",
        "# Key Findings\n_Important analytical conclusions from this project. Referenced by finding ID for traceability._\nOld fact.",
    )
    path.write_text(content, encoding="utf-8")

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="# Key Findings\nNew fact.",
    )
    messages = [Message(role="user", content="test")]
    await mgr.extract_memories(messages, provider)
    final = path.read_text(encoding="utf-8")
    assert "Old fact" in final
    assert "New fact" in final


async def test_extraction_prompt_includes_existing_memory(tmp_path):
    """The prompt sent to the LLM includes existing memory for deduplication."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Add real content so load_memory returns something
    path.write_text(
        "# Data Source Knowledge\norders table has 2M rows.\n",
        encoding="utf-8",
    )
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="")
    messages = [Message(role="user", content="test")]
    await mgr.extract_memories(messages, provider)
    # Inspect the prompt sent to the LLM
    call_args = provider.chat.call_args
    prompt_msg = call_args[0][0][0]  # first positional arg, first message
    assert "orders table" in prompt_msg.content


async def test_extraction_prompt_includes_recent_turns(tmp_path):
    """The prompt sent to the LLM includes content from recent messages."""
    mgr = MemoryManager(extract_frequency=5, project_dir=tmp_path)
    messages = [
        Message(role="user", content=f"Turn {i}") for i in range(10)
    ]
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="")
    await mgr.extract_memories(messages, provider)
    call_args = provider.chat.call_args
    prompt_msg = call_args[0][0][0]
    # Should include recent turns (last freq*2 = 10 messages)
    assert "Turn 9" in prompt_msg.content
    assert "Turn 5" in prompt_msg.content
