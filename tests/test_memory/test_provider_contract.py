"""Contract tests any MemoryProvider implementation must pass.

Parametrized by provider factory — run all tests against every impl.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest

from yigthinker.memory.provider import MemoryProvider, MemoryRecord


def _record(id_: str, session: str | None = "s1", kind: str = "pattern", content: str = "hello") -> MemoryRecord:
    return MemoryRecord(
        id=id_,
        kind=kind,  # type: ignore[arg-type]
        content=content,
        session_id=session,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def provider(tmp_path: Path) -> AsyncIterator[MemoryProvider]:
    """Default provider fixture — overridden per impl in that impl's test file."""
    from yigthinker.memory.provider import FileMemoryProvider
    p = FileMemoryProvider(store_dir=tmp_path, agent_id="test")
    yield p


@pytest.mark.asyncio
async def test_write_then_read_round_trip(provider: MemoryProvider):
    rec = _record("r1")
    await provider.write(rec)
    got = await provider.read()
    assert len(got) == 1
    assert got[0].id == "r1"
    assert got[0].content == "hello"


@pytest.mark.asyncio
async def test_read_filters_by_kind(provider: MemoryProvider):
    await provider.write(_record("r1", kind="pattern"))
    await provider.write(_record("r2", kind="user_fact"))
    patterns = await provider.read(kind="pattern")
    assert [r.id for r in patterns] == ["r1"]


@pytest.mark.asyncio
async def test_read_filters_by_session(provider: MemoryProvider):
    await provider.write(_record("r1", session="sA"))
    await provider.write(_record("r2", session="sB"))
    sa = await provider.read(session_id="sA")
    assert [r.id for r in sa] == ["r1"]


@pytest.mark.asyncio
async def test_read_respects_limit(provider: MemoryProvider):
    for i in range(10):
        await provider.write(_record(f"r{i}"))
    got = await provider.read(limit=3)
    assert len(got) == 3


@pytest.mark.asyncio
async def test_delete_tombstones_record(provider: MemoryProvider):
    await provider.write(_record("r1"))
    assert await provider.delete("r1") is True
    got = await provider.read()
    assert got == []


@pytest.mark.asyncio
async def test_delete_missing_returns_false(provider: MemoryProvider):
    assert await provider.delete("nope") is False


@pytest.mark.asyncio
async def test_list_sessions_returns_distinct(provider: MemoryProvider):
    await provider.write(_record("r1", session="sA"))
    await provider.write(_record("r2", session="sA"))
    await provider.write(_record("r3", session="sB"))
    await provider.write(_record("r4", session=None))   # cross-session record
    sessions = await provider.list_sessions()
    assert sorted(sessions) == ["sA", "sB"]   # None is excluded


@pytest.mark.asyncio
async def test_cross_session_records_returned_when_no_filter(provider: MemoryProvider):
    await provider.write(_record("r1", session=None))
    await provider.write(_record("r2", session="s1"))
    all_ = await provider.read()
    assert {r.id for r in all_} == {"r1", "r2"}
