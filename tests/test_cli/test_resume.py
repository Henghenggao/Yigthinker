import time
from pathlib import Path

from yigthinker.__main__ import _hydrate_session_from_resume
from yigthinker.persistence import TranscriptReader, TranscriptWriter, find_latest_session
from yigthinker.session import SessionContext


def test_transcript_round_trip(tmp_path):
    path = tmp_path / "session.jsonl"
    writer = TranscriptWriter(path)
    writer.append("user", "show me revenue")
    writer.append("assistant", "Here is the revenue data...")

    reader = TranscriptReader(path)
    messages = reader.to_messages()
    assert len(messages) == 2
    assert messages[0].content == "show me revenue"
    assert messages[1].content == "Here is the revenue data..."


def test_latest_session_path(tmp_path):
    sessions_dir = tmp_path / ".yigthinker" / "sessions"
    sessions_dir.mkdir(parents=True)
    s1 = sessions_dir / "session_001.jsonl"
    s2 = sessions_dir / "session_002.jsonl"
    s1.write_text("")
    time.sleep(0.01)
    s2.write_text("")

    latest = find_latest_session(sessions_dir)
    assert latest == s2


def test_resume_hydrates_context_messages(tmp_path, monkeypatch):
    home = tmp_path
    sessions_dir = home / ".yigthinker" / "sessions"
    sessions_dir.mkdir(parents=True)
    transcript = sessions_dir / "session_123.jsonl"
    writer = TranscriptWriter(transcript)
    writer.append("user", "show revenue")
    writer.append("assistant", "Revenue is up")

    monkeypatch.setattr(Path, "home", lambda: home)
    ctx = SessionContext()
    _hydrate_session_from_resume(ctx, True)

    assert ctx.transcript_path == str(transcript)
    assert len(ctx.messages) == 2
    assert ctx.messages[0].content == "show revenue"
