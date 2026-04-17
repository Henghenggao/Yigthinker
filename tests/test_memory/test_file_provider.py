from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yigthinker.memory.provider import FileMemoryProvider, MemoryRecord


def _rec(id_: str, kind: str = "pattern") -> MemoryRecord:
    return MemoryRecord(
        id=id_,
        kind=kind,   # type: ignore[arg-type]
        content=f"content-{id_}",
        session_id="s1",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_jsonl_file_format(tmp_path: Path):
    p = FileMemoryProvider(store_dir=tmp_path, agent_id="agent-a")
    await p.write(_rec("r1"))
    await p.write(_rec("r2"))
    path = tmp_path / "agent-a.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "id" in obj and "content" in obj


@pytest.mark.asyncio
async def test_tombstone_hides_deleted_but_keeps_file_line(tmp_path: Path):
    p = FileMemoryProvider(store_dir=tmp_path, agent_id="a")
    await p.write(_rec("r1"))
    await p.delete("r1")
    path = tmp_path / "a.jsonl"
    # 2 lines: original + tombstone
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    # read() hides tombstoned
    assert await p.read() == []


@pytest.mark.asyncio
async def test_compaction_triggers_on_threshold(tmp_path: Path):
    p = FileMemoryProvider(store_dir=tmp_path, agent_id="a", max_records_before_compact=5)
    for i in range(3):
        await p.write(_rec(f"r{i}"))
        await p.delete(f"r{i}")      # 6 lines (3 writes + 3 tombstones) -> triggers
    path = tmp_path / "a.jsonl"
    # After compaction, tombstoned records are dropped — file should be empty or
    # contain only records still active.
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 0


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_lose_records(tmp_path: Path):
    p = FileMemoryProvider(store_dir=tmp_path, agent_id="a")

    async def _write_many(start: int):
        for i in range(start, start + 20):
            await p.write(_rec(f"r{i}"))

    await asyncio.gather(_write_many(0), _write_many(100), _write_many(200))
    got = await p.read(limit=1000)
    assert len({r.id for r in got}) == 60


@pytest.mark.asyncio
async def test_different_agent_ids_isolated(tmp_path: Path):
    p1 = FileMemoryProvider(store_dir=tmp_path, agent_id="alice")
    p2 = FileMemoryProvider(store_dir=tmp_path, agent_id="bob")
    await p1.write(_rec("r1"))
    assert len(await p1.read()) == 1
    assert len(await p2.read()) == 0


@pytest.mark.asyncio
async def test_write_triggers_compaction_without_deadlock(tmp_path: Path):
    # Regression: write() → _compact_locked() → _read_active() re-enters the
    # same FileLock. Relies on the cached _file_lock being reentrant in-process.
    # If the cache is ever replaced with a fresh per-call FileLock, this hangs.
    async def _run() -> list[MemoryRecord]:
        p = FileMemoryProvider(
            store_dir=tmp_path, agent_id="a", max_records_before_compact=2
        )
        for i in range(3):
            await p.write(_rec(f"r{i}"))
        return await p.read()

    records = await asyncio.wait_for(_run(), timeout=5.0)
    assert len(records) == 3
