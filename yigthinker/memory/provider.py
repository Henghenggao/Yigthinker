"""MemoryProvider — agent-private session-scoped memory abstraction.

IMPORTANT (spec §4.5.2 one-vote veto): MemoryProvider is strictly separate
from RetrievalProvider (enterprise RAG). Do not conflate.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from filelock import FileLock
from pydantic import BaseModel, Field


MemoryKind = Literal["pattern", "preference", "session_summary", "user_fact"]


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: MemoryKind
    content: str
    session_id: str | None = None      # None = cross-session (agent-wide)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MemoryProvider(Protocol):
    async def write(self, record: MemoryRecord) -> None: ...
    async def read(
        self,
        kind: MemoryKind | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]: ...
    async def delete(self, record_id: str) -> bool: ...
    async def list_sessions(self) -> list[str]: ...
