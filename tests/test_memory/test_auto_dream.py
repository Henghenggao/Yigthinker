from __future__ import annotations
import time
import pytest
from pathlib import Path
from yigthinker.memory.auto_dream import DreamState, AutoDream, AutoDreamConfig


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
