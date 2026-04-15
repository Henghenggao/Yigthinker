# tests/test_persistence.py
import json
from yigthinker.persistence import TranscriptWriter, TranscriptReader


def test_writer_creates_file_and_appends(tmp_path):
    path = tmp_path / "session.jsonl"
    writer = TranscriptWriter(path)
    writer.append("user", "hello")
    writer.append("assistant", "hi there")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    entry = json.loads(lines[0])
    assert entry["role"] == "user"
    assert entry["message"]["content"] == "hello"
    assert "timestamp" in entry


def test_writer_creates_parent_dirs(tmp_path):
    path = tmp_path / "sessions" / "2026" / "session.jsonl"
    writer = TranscriptWriter(path)
    writer.append("user", "test")
    assert path.exists()


def test_reader_load_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    reader = TranscriptReader(path)
    assert reader.load() == []


def test_reader_load_entries(tmp_path):
    path = tmp_path / "session.jsonl"
    writer = TranscriptWriter(path)
    writer.append("user", "hello")
    writer.append("assistant", "hi")
    reader = TranscriptReader(path)
    entries = reader.load()
    assert len(entries) == 2
    assert entries[0]["role"] == "user"


def test_reader_to_messages(tmp_path):
    path = tmp_path / "session.jsonl"
    writer = TranscriptWriter(path)
    writer.append("user", "hello")
    writer.append("assistant", "hi")
    writer.append("tool", {"tool_name": "echo", "content": "result"})  # skipped
    messages = TranscriptReader(path).to_messages()
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


def test_reader_missing_file_returns_empty(tmp_path):
    reader = TranscriptReader(tmp_path / "nonexistent.jsonl")
    assert reader.load() == []
