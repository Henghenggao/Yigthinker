"""Tests for RPAStateStore — clone of test_dedup.py shape."""
from __future__ import annotations

from pathlib import Path

import pytest

from yigthinker.presence.gateway.rpa_state import RPAStateStore


@pytest.fixture
def rpa_state(tmp_path: Path):
    store = RPAStateStore(db_path=tmp_path / "state.db")
    yield store
    store.close()


def test_schema_bootstrap_idempotent(tmp_path: Path) -> None:
    """RPAStateStore can be instantiated twice against the same file without error."""
    db = tmp_path / "state.db"
    s1 = RPAStateStore(db_path=db)
    s1.close()
    s2 = RPAStateStore(db_path=db)
    # Assert the 3 tables exist
    conn = s2._conn
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "callback_dedup" in tables
    assert "checkpoint_attempts" in tables
    assert "workflow_llm_calls" in tables
    s2.close()


def test_survives_reopen(tmp_path: Path) -> None:
    """State persists across process restart (sqlite file-backed)."""
    db = tmp_path / "state.db"
    s1 = RPAStateStore(db_path=db)
    s1.record_callback("cb-1", {"action": "skip", "reason": "test"})
    s1.close()

    s2 = RPAStateStore(db_path=db)
    cached = s2.get_cached_decision("cb-1")
    assert cached == {"action": "skip", "reason": "test"}
    s2.close()


def test_is_duplicate_callback_first_time(rpa_state: RPAStateStore) -> None:
    assert rpa_state.is_duplicate_callback("cb-new") is False


def test_record_callback_then_duplicate(rpa_state: RPAStateStore) -> None:
    rpa_state.record_callback("cb-1", {"action": "escalate", "reason": "test"})
    assert rpa_state.is_duplicate_callback("cb-1") is True
    assert rpa_state.get_cached_decision("cb-1") == {"action": "escalate", "reason": "test"}


def test_record_checkpoint_attempt_returns_count(rpa_state: RPAStateStore) -> None:
    """Count reflects rolling 24h window per (workflow, checkpoint)."""
    n1 = rpa_state.record_checkpoint_attempt("wf-a", "ckpt-1")
    n2 = rpa_state.record_checkpoint_attempt("wf-a", "ckpt-1")
    n3 = rpa_state.record_checkpoint_attempt("wf-a", "ckpt-1")
    assert n1 == 1
    assert n2 == 2
    assert n3 == 3
    # Different checkpoint — isolated
    assert rpa_state.record_checkpoint_attempt("wf-a", "ckpt-2") == 1
    # Different workflow — isolated
    assert rpa_state.record_checkpoint_attempt("wf-b", "ckpt-1") == 1


def test_record_llm_call_returns_day_count(rpa_state: RPAStateStore) -> None:
    """UTC day bucket count increments per workflow."""
    n1 = rpa_state.record_llm_call("wf-a")
    n2 = rpa_state.record_llm_call("wf-a")
    assert n1 == 1
    assert n2 == 2
    # Different workflow — isolated
    assert rpa_state.record_llm_call("wf-b") == 1


def test_prune_expired_dedup(tmp_path: Path) -> None:
    """TTL prune removes dedup rows older than 24h on insert."""
    import time
    store = RPAStateStore(db_path=tmp_path / "state.db")
    # Manually inject an old row
    store._conn.execute(
        "INSERT INTO callback_dedup (callback_id, seen_at, decision_json) VALUES (?, ?, ?)",
        ("old-id", time.time() - 86400 - 100, '{"action":"skip"}'),
    )
    store._conn.commit()
    # Trigger prune via new insert
    store.record_callback("new-id", {"action": "skip"})
    row = store._conn.execute(
        "SELECT 1 FROM callback_dedup WHERE callback_id = ?", ("old-id",)
    ).fetchone()
    assert row is None
    store.close()
