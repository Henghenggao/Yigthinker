from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from yigthinker.types import Message


class TranscriptWriter:
    """Append JSONL entries to a session transcript file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, role: str, content: object) -> None:
        entry = {
            "role": role,
            "message": {"content": content},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class TranscriptReader:
    """Read and parse a JSONL session transcript."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[dict]:
        if not self._path.exists():
            return []
        entries = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def to_messages(self) -> list[Message]:
        """Return only user/assistant entries as Message objects (skip tool entries)."""
        return [
            Message(role=e["role"], content=e["message"]["content"])
            for e in self.load()
            if e["role"] in ("user", "assistant")
        ]


def find_latest_session(sessions_dir: Path) -> Path | None:
    """Return the most recently modified .jsonl file in sessions_dir."""
    files = sorted(sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None
