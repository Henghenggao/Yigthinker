"""Tests for PatternStore (Phase 10 BHV-04): filelocked + atomic-write JSON store
for detected automation patterns with lazy 90-day suppression expiry.

These tests were written BEFORE the implementation lands (Wave 0 / RED phase).
They will only pass once `yigthinker/memory/patterns.py` is created in Task 1.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def store(tmp_path: Path):
    """Create a PatternStore backed by a temporary patterns.json."""
    from yigthinker.memory.patterns import PatternStore

    return PatternStore(path=tmp_path / "patterns.json")


def _make_pattern(
    pattern_id: str = "sales_monthly_aggregation",
    frequency: int = 5,
    suppressed: bool = False,
    suppressed_until: str | None = None,
) -> dict:
    return {
        "pattern_id": pattern_id,
        "description": "Load sales data, aggregate by month, chart results",
        "tool_sequence": ["sql_query", "df_transform", "chart_create"],
        "frequency": frequency,
        "estimated_time_saved_minutes": 15,
        "required_connections": ["sqlite"],
        "first_seen": "2026-04-01T10:00:00+00:00",
        "last_seen": "2026-04-10T14:30:00+00:00",
        "sessions": ["session-abc", "session-def", "session-ghi"],
        "suppressed": suppressed,
        "suppressed_until": suppressed_until,
    }


def test_load_empty_returns_default_shape(store) -> None:
    """load() on a missing file returns {'patterns': {}} without touching disk."""
    data = store.load()
    assert data == {"patterns": {}}
    # Loading an empty store must NOT create the file on disk (read-only op).
    assert not store._path.exists()


def test_save_creates_atomic_file(store) -> None:
    """save() writes patterns.json atomically via tempfile + os.replace."""
    p = _make_pattern()
    store.save({"patterns": {p["pattern_id"]: p}})

    assert store._path.exists()
    on_disk = json.loads(store._path.read_text(encoding="utf-8"))
    assert "patterns" in on_disk
    assert "sales_monthly_aggregation" in on_disk["patterns"]
    assert on_disk["patterns"]["sales_monthly_aggregation"]["frequency"] == 5

    # No .tmp files left behind
    leftover = list(store._path.parent.glob("*.tmp"))
    assert leftover == []


def test_suppress_writes_90_day_default(store) -> None:
    """suppress(pattern_id) without a days argument sets suppressed_until to ~now+90d."""
    p = _make_pattern()
    store.save({"patterns": {p["pattern_id"]: p}})

    before = datetime.now(timezone.utc)
    ok = store.suppress(p["pattern_id"])
    after = datetime.now(timezone.utc)

    assert ok is True
    reloaded = store.load()
    entry = reloaded["patterns"][p["pattern_id"]]
    assert entry["suppressed"] is True
    assert entry["suppressed_until"] is not None
    until = datetime.fromisoformat(entry["suppressed_until"])
    # Default is 90 days; accept a 1-second clock skew window on both sides.
    assert before + timedelta(days=90) - timedelta(seconds=1) <= until
    assert until <= after + timedelta(days=90) + timedelta(seconds=1)


def test_suppress_90_day_expiry(store) -> None:
    """suppress(pid, days=90) encodes the 90-day expiry in suppressed_until (BHV-04)."""
    p = _make_pattern()
    store.save({"patterns": {p["pattern_id"]: p}})

    ok = store.suppress(p["pattern_id"], days=90)
    assert ok is True

    entry = store.load()["patterns"][p["pattern_id"]]
    assert entry["suppressed"] is True
    until = datetime.fromisoformat(entry["suppressed_until"])
    delta = until - datetime.now(timezone.utc)
    # Allow a few seconds of slop. MUST be within [89.9, 90.1] days.
    assert timedelta(days=89, hours=23, minutes=59) <= delta <= timedelta(days=90, minutes=1)


def test_suppress_missing_pattern_returns_false(store) -> None:
    """Suppressing a pattern_id that doesn't exist returns False without mutating the store."""
    store.save({"patterns": {}})
    ok = store.suppress("nonexistent_pattern")
    assert ok is False
    assert store.load()["patterns"] == {}


def test_list_active_filters_by_min_frequency(store) -> None:
    """list_active(min_frequency=3) excludes patterns with frequency < 3."""
    store.save({
        "patterns": {
            "a": _make_pattern("a", frequency=2),
            "b": _make_pattern("b", frequency=5),
            "c": _make_pattern("c", frequency=1),
        }
    })
    active = store.list_active(min_frequency=3)
    ids = {p["pattern_id"] for p in active}
    assert ids == {"b"}


def test_list_active_default_hides_suppressed(store) -> None:
    """list_active() defaults to hiding patterns with suppressed=True AND suppressed_until > now."""
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    store.save({
        "patterns": {
            "visible": _make_pattern("visible", frequency=5),
            "hidden": _make_pattern("hidden", frequency=5, suppressed=True, suppressed_until=future),
        }
    })
    active = store.list_active()
    ids = {p["pattern_id"] for p in active}
    assert ids == {"visible"}


def test_list_active_include_suppressed_true(store) -> None:
    """list_active(include_suppressed=True) returns suppressed entries too."""
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    store.save({
        "patterns": {
            "a": _make_pattern("a", frequency=5),
            "b": _make_pattern("b", frequency=5, suppressed=True, suppressed_until=future),
        }
    })
    active = store.list_active(include_suppressed=True)
    ids = {p["pattern_id"] for p in active}
    assert ids == {"a", "b"}


def test_lazy_prune_expired_suppression(store) -> None:
    """CORR-04a: suppression with suppressed_until < now is lazily cleared at read time.

    The on-disk entry must have suppressed=False + suppressed_until=None after the read,
    and the pattern must reappear in list_active().
    """
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    p = _make_pattern("expired_one", suppressed=True, suppressed_until=past)
    store.save({"patterns": {p["pattern_id"]: p}})

    # Reading triggers lazy prune.
    active = store.list_active()
    assert any(row["pattern_id"] == "expired_one" for row in active)

    # The prune must be persisted — reload from disk and check fields.
    reloaded = store.load()
    entry = reloaded["patterns"]["expired_one"]
    assert entry["suppressed"] is False
    assert entry["suppressed_until"] is None


def test_save_locked_helper_exists_for_reentrancy(store) -> None:
    """Pitfall 5: PatternStore must expose a `_save_locked` helper so `suppress` can
    avoid nested lock acquisition. Tests that the helper is callable and does NOT
    itself acquire the lock (no `with self._lock:` inside)."""
    import inspect
    from yigthinker.memory.patterns import PatternStore

    assert hasattr(PatternStore, "_save_locked"), (
        "PatternStore must have a `_save_locked` helper that writes without "
        "acquiring the lock (called from `suppress` which already holds it)."
    )
    src = inspect.getsource(PatternStore._save_locked)
    # The helper itself must NOT contain `with self._lock:` — that would deadlock
    # under non-reentrant filelock backends.
    assert "with self._lock:" not in src


def test_suppress_then_save_roundtrip_no_deadlock(store) -> None:
    """End-to-end reentrancy smoke test: suppress() must complete without deadlocking
    even though it internally writes the store while the lock is held."""
    p = _make_pattern()
    store.save({"patterns": {p["pattern_id"]: p}})
    ok = store.suppress(p["pattern_id"])
    assert ok is True
    # A subsequent load() must see the suppression.
    assert store.load()["patterns"][p["pattern_id"]]["suppressed"] is True
