from __future__ import annotations

from pathlib import Path

from yigthinker.persistence import TranscriptWriter


def create_subagent_transcript_writer(
    session_id: str,
    subagent_id: str,
) -> TranscriptWriter:
    """Create a TranscriptWriter for a subagent (SPAWN-17, D-15).

    Path: ~/.yigthinker/sessions/subagents/{session_id}/{subagent_id}.jsonl
    """
    base = Path.home() / ".yigthinker" / "sessions" / "subagents" / session_id
    path = base / f"{subagent_id}.jsonl"
    return TranscriptWriter(path)
