from __future__ import annotations
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from yigthinker.memory.auto_dream import DreamState, AutoDream, AutoDreamConfig
from yigthinker.types import LLMResponse


def test_dream_state_initially_zero(tmp_path):
    state = DreamState(tmp_path / ".dream_state")
    assert state.last_timestamp == 0
    assert state.hours_since_last() > 1000  # very old (epoch)


def test_dream_state_update_and_reload(tmp_path):
    path = tmp_path / ".dream_state"
    state = DreamState(path)
    state.update()
    state2 = DreamState(path)
    # After update, hours_since_last should be nearly 0
    assert state2.hours_since_last() < 0.01


def test_should_dream_when_thresholds_met(tmp_path):
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    # Create 2 session files
    (sessions_dir / "s1.jsonl").write_text("")
    (sessions_dir / "s2.jsonl").write_text("")

    state = DreamState(tmp_path / ".dream_state")
    dream = AutoDream(config=config, sessions_dir=sessions_dir, state=state)
    assert dream.should_run() is True


def test_should_not_dream_when_not_enough_sessions(tmp_path):
    config = AutoDreamConfig(min_hours=0, min_sessions=5)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    state = DreamState(tmp_path / ".dream_state")
    dream = AutoDream(config=config, sessions_dir=sessions_dir, state=state)
    assert dream.should_run() is False


def test_list_sessions_since_last(tmp_path):
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    state = DreamState(tmp_path / ".dream_state")
    dream = AutoDream(config=config, sessions_dir=sessions_dir, state=state)
    sessions = dream.list_sessions_since_last()
    assert len(sessions) == 1


def test_list_sessions_excludes_old_files(tmp_path):
    """Files modified before last dream should be excluded."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    # Create a session file
    f = sessions_dir / "old.jsonl"
    f.write_text("")

    # Update state (marks current time as last dream)
    state = DreamState(tmp_path / ".dream_state")
    state.update()

    # Create another file AFTER the state update
    import time as _time
    _time.sleep(0.01)
    new_f = sessions_dir / "new.jsonl"
    new_f.write_text("")

    dream = AutoDream(config=config, sessions_dir=sessions_dir, state=state)
    sessions = dream.list_sessions_since_last()
    names = [s.name for s in sessions]
    assert "new.jsonl" in names
    assert "old.jsonl" not in names


async def test_run_background_updates_state(tmp_path):
    """run_background should update DreamState after running."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text("")

    dream = AutoDream(config=config, sessions_dir=sessions_dir, state=state)
    await dream.run_background(memory_path, active_session_id="other-session")

    # State should have been updated (timestamp close to now)
    assert state.hours_since_last() < 0.01


async def test_dream_consolidation_calls_llm(tmp_path):
    """run_background sends session memories to LLM and writes global MEMORY.md."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    # Create a session file
    (sessions_dir / "s1.jsonl").write_text("")
    # Create a corresponding MEMORY.md in a project memory dir
    mem_dir = tmp_path / "project_mem"
    mem_dir.mkdir()
    mem_file = mem_dir / "MEMORY.md"
    mem_file.write_text("# Key Findings\nSales grew 10% in Q3.\n")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="# Key Findings\nSales grew 10% in Q3 (consolidated).",
    )
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[mem_dir],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    provider.chat.assert_called_once()
    assert memory_path.exists()
    content = memory_path.read_text(encoding="utf-8")
    assert "consolidated" in content


async def test_dream_writes_global_memory(tmp_path):
    """After run_background completes, global MEMORY.md exists with consolidated content."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    mem_dir = tmp_path / "proj_mem"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text("# Key Findings\nFact A.\n")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="# Key Findings\nFact A (merged).",
    )
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[mem_dir],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    assert memory_path.exists()
    assert "Fact A (merged)" in memory_path.read_text(encoding="utf-8")


async def test_dream_prunes_when_over_4k(tmp_path):
    """Dream prompt includes pruning instruction for ~4K tokens."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    mem_dir = tmp_path / "proj_mem"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text("# Key Findings\nSome fact.\n")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="pruned")
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[mem_dir],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    # Check the prompt sent to provider includes pruning instruction
    call_args = provider.chat.call_args
    prompt_msg = call_args[0][0][0]
    assert "4000 tokens" in prompt_msg.content


async def test_dream_reads_session_memories(tmp_path):
    """Dream reads MEMORY.md from multiple session project dirs."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")
    (sessions_dir / "s2.jsonl").write_text("")

    # Create two project memory dirs
    mem_dir1 = tmp_path / "proj1"
    mem_dir1.mkdir()
    (mem_dir1 / "MEMORY.md").write_text("# Key Findings\nFact from project 1.\n")
    mem_dir2 = tmp_path / "proj2"
    mem_dir2.mkdir()
    (mem_dir2 / "MEMORY.md").write_text("# Key Findings\nFact from project 2.\n")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="merged")
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[mem_dir1, mem_dir2],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    call_args = provider.chat.call_args
    prompt_msg = call_args[0][0][0]
    assert "project 1" in prompt_msg.content
    assert "project 2" in prompt_msg.content


async def test_dream_updates_state_after_success(tmp_path):
    """After successful dream with LLM, state timestamp is updated."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.jsonl").write_text("")

    mem_dir = tmp_path / "proj_mem"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text("# Key Findings\nSome fact.\n")

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(stop_reason="end_turn", text="done")
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[mem_dir],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    assert state.hours_since_last() < 0.01


async def test_dream_skips_when_no_sessions(tmp_path):
    """If no session files exist, LLM is not called."""
    config = AutoDreamConfig(min_hours=0, min_sessions=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    # No session files

    state = DreamState(tmp_path / ".dream_state")
    memory_path = tmp_path / "global" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    provider = AsyncMock()
    dream = AutoDream(
        config=config, sessions_dir=sessions_dir, state=state,
        memory_dirs=[],
    )
    await dream.run_background(memory_path, "other-session", provider=provider)
    provider.chat.assert_not_called()
