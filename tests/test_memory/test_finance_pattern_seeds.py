"""Yigfinance Track D: pre-seed PatternStore with canonical finance rituals.

2026-04-18 ADR-011: without seeds, `suggest_automation` surfaces nothing
on a fresh install because PatternStore starts empty. The architect-not-
executor value prop is invisible for the first several sessions. Pre-
seeding with 6 canonical finance patterns (monthly_close, quarterly
budget review, AR aging, cash flow forecast, expense reimbursement, year-
end close) closes that gap — a day-one `suggest_automation` call returns
meaningful suggestions the user can evaluate.

Seeds use the pattern_id prefix ``finance_seed:`` so they are
distinguishable from patterns auto-detected by AutoDream. The seeding
function is idempotent — re-running it never duplicates or overwrites
existing seeds, and the user's own suppressions of seed patterns are
preserved across calls.
"""
from __future__ import annotations

import pytest

from yigthinker.memory.finance_pattern_seeds import (
    FINANCE_SEEDS,
    seed_finance_patterns,
)
from yigthinker.memory.patterns import PatternStore


# ---------------------------------------------------------------------------
# FINANCE_SEEDS: the data contract
# ---------------------------------------------------------------------------

def test_finance_seeds_has_six_canonical_patterns():
    """ADR-011 Track D commits to six patterns — lock the exact set."""
    expected_ids = {
        "finance_seed:monthly_close",
        "finance_seed:quarterly_budget_review",
        "finance_seed:recurring_aging_report",
        "finance_seed:cash_flow_forecast",
        "finance_seed:expense_reimbursement_review",
        "finance_seed:year_end_close",
    }
    assert set(FINANCE_SEEDS.keys()) == expected_ids


def test_every_seed_has_required_fields():
    """Each seed must carry the full pattern schema so PatternStore
    consumers don't need to special-case seeded entries."""
    required = {
        "pattern_id", "description", "tool_sequence", "frequency",
        "estimated_time_saved_minutes", "required_connections",
    }
    for pid, entry in FINANCE_SEEDS.items():
        missing = required - entry.keys()
        assert not missing, f"{pid} missing fields: {missing}"
        # All seeds start unsuppressed — users can suppress any seed
        # they don't care about, which persists on disk.
        assert entry.get("suppressed", False) is False


def test_seed_tool_sequences_reference_real_tools():
    """Every tool named in a seed's tool_sequence must actually exist in
    the registry — otherwise suggest_automation surfaces a pattern that
    references ghosts."""
    from yigthinker.registry_factory import build_tool_registry
    from yigthinker.tools.sql.connection import ConnectionPool
    registry = build_tool_registry(pool=ConnectionPool())
    real_tools = set(registry.names())
    # Add the optional workflow family (registered only when Jinja2 is
    # available — in tests it always is, but be defensive)
    real_tools.update({
        "workflow_generate", "workflow_deploy", "workflow_manage",
        "suggest_automation",
    })

    for pid, entry in FINANCE_SEEDS.items():
        for tool in entry["tool_sequence"]:
            assert tool in real_tools, (
                f"{pid} references non-existent tool {tool!r}"
            )


def test_estimated_time_saved_is_positive_integer():
    """Time-saved is what makes a suggestion valuable. Zero or negative
    values are bugs."""
    for pid, entry in FINANCE_SEEDS.items():
        val = entry["estimated_time_saved_minutes"]
        assert isinstance(val, int)
        assert val > 0, f"{pid} has non-positive time saved: {val}"


def test_pattern_ids_are_seed_prefixed():
    """The ``finance_seed:`` prefix is the contract that lets readers
    distinguish canned seeds from AutoDream-detected patterns. Breaking
    it would confuse downstream consumers."""
    for pid in FINANCE_SEEDS:
        assert pid.startswith("finance_seed:"), (
            f"{pid} must use the 'finance_seed:' prefix"
        )


# ---------------------------------------------------------------------------
# seed_finance_patterns: the idempotent loader
# ---------------------------------------------------------------------------

def test_seed_writes_all_six_to_empty_store(tmp_path):
    """First run on an empty store: every seed is persisted; return
    value is the count of new patterns added (= 6)."""
    store = PatternStore(path=tmp_path / "patterns.json")
    added = seed_finance_patterns(store)
    assert added == 6
    patterns = store.load()["patterns"]
    assert len(patterns) == 6
    assert set(patterns) == set(FINANCE_SEEDS)


def test_seed_is_idempotent(tmp_path):
    """Re-running on a store that already has seeds adds zero new entries
    and never overwrites existing ones — this is the guarantee that lets
    build_app call seed_finance_patterns unconditionally on every boot."""
    store = PatternStore(path=tmp_path / "patterns.json")
    first = seed_finance_patterns(store)
    second = seed_finance_patterns(store)
    third = seed_finance_patterns(store)
    assert first == 6
    assert second == 0
    assert third == 0


def test_seed_preserves_user_suppressions(tmp_path):
    """If the user has suppressed a seed, re-running the seeder must
    keep the suppression state intact — do not undo a user choice."""
    store = PatternStore(path=tmp_path / "patterns.json")
    seed_finance_patterns(store)
    suppressed_ok = store.suppress("finance_seed:year_end_close", days=365)
    assert suppressed_ok

    # Run seeder again — suppression must survive
    seed_finance_patterns(store)
    entry = store.load()["patterns"]["finance_seed:year_end_close"]
    assert entry["suppressed"] is True
    assert entry["suppressed_until"] is not None


def test_seed_coexists_with_user_detected_patterns(tmp_path):
    """AutoDream-detected patterns have different pattern_ids (no
    'finance_seed:' prefix). Seeding must not disturb them."""
    store = PatternStore(path=tmp_path / "patterns.json")
    # Simulate an AutoDream-detected pattern already in the store
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    data = store.load()
    data["patterns"]["user_detected:weekly_rollup"] = {
        "pattern_id": "user_detected:weekly_rollup",
        "description": "weekly rollup detected from sessions",
        "tool_sequence": ["sql_query", "chart_create"],
        "frequency": 3,
        "estimated_time_saved_minutes": 20,
        "required_connections": ["finance"],
        "first_seen": now,
        "last_seen": now,
        "sessions": ["s1", "s2", "s3"],
        "suppressed": False,
        "suppressed_until": None,
    }
    store.save(data)

    added = seed_finance_patterns(store)
    assert added == 6

    all_patterns = store.load()["patterns"]
    # User's pattern survives untouched
    assert "user_detected:weekly_rollup" in all_patterns
    assert all_patterns["user_detected:weekly_rollup"]["frequency"] == 3
    # All 6 seeds landed
    for pid in FINANCE_SEEDS:
        assert pid in all_patterns


def test_seed_sets_sensible_timestamps(tmp_path):
    """first_seen / last_seen must be ISO 8601 UTC strings so downstream
    consumers (list_active, suggest_automation) can parse them."""
    from datetime import datetime
    store = PatternStore(path=tmp_path / "patterns.json")
    seed_finance_patterns(store)

    for pid, entry in store.load()["patterns"].items():
        assert entry["first_seen"]
        assert entry["last_seen"]
        # Should parse cleanly as ISO 8601
        datetime.fromisoformat(entry["first_seen"])
        datetime.fromisoformat(entry["last_seen"])
