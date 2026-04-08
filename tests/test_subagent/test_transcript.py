# tests/test_subagent/test_transcript.py
# Transcript persistence tests (SPAWN-17, D-15).
import json
from pathlib import Path
from unittest.mock import patch

from yigthinker.subagent.transcript import create_subagent_transcript_writer


def test_transcript_path():
    """create_subagent_transcript_writer produces correct path under subagents dir."""
    writer = create_subagent_transcript_writer("session-abc", "subagent-123")
    expected_suffix = (
        Path(".yigthinker") / "sessions" / "subagents" / "session-abc" / "subagent-123.jsonl"
    )
    # The path should end with the expected components
    actual = Path(writer._path)
    assert actual.name == "subagent-123.jsonl"
    assert actual.parent.name == "session-abc"
    assert actual.parent.parent.name == "subagents"
    assert actual.parent.parent.parent.name == "sessions"


def test_transcript_write(tmp_path: Path):
    """writer.append() creates valid JSONL entries."""
    path = tmp_path / "test-transcript.jsonl"

    # Manually create a TranscriptWriter at the tmp_path location
    from yigthinker.persistence import TranscriptWriter
    writer = TranscriptWriter(path)

    writer.append("assistant", "result text")
    writer.append("user", "follow up question")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    entry1 = json.loads(lines[0])
    assert entry1["role"] == "assistant"
    assert entry1["message"]["content"] == "result text"
    assert "timestamp" in entry1

    entry2 = json.loads(lines[1])
    assert entry2["role"] == "user"
    assert entry2["message"]["content"] == "follow up question"
