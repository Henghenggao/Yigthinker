"""suggest_automation must surface finance seeds regardless of frequency.

2026-04-18 Yigfinance slice-1 UAT exposed the semantic gap: PatternStore
seeds carry ``frequency=1`` (they are canonical rituals Yigfinance ships,
not patterns observed via AutoDream cross-session detection), so they
were filtered out by the tool's default ``min_frequency=2`` threshold.
Result: ``suggest_automation`` returned empty on a fresh install — the
architect-not-executor value prop stayed invisible day one, exactly the
gap ADR-011 Track D was supposed to close.

Fix contract: entries with a ``finance_seed:`` pattern-id prefix are
always included (subject only to the ``include_suppressed`` filter);
they coexist with AutoDream-detected entries, which continue to respect
the frequency threshold.

The output also surfaces an ``is_seed`` flag so the LLM can narrate
honestly: "you're new here, but we ship N canonical finance rituals —
any apply to you?" instead of pretending the seeds were observed.
"""
from __future__ import annotations

import pytest

from yigthinker.memory.patterns import PatternStore
from yigthinker.tools.workflow.suggest_automation import (
    SuggestAutomationInput,
    SuggestAutomationTool,
)


@pytest.fixture
def seeded_store(tmp_path):
    """PatternStore with the 6 finance seeds loaded + one AutoDream-style
    user pattern, for a realistic mixed state."""
    from yigthinker.memory.finance_pattern_seeds import seed_finance_patterns
    store = PatternStore(path=tmp_path / "patterns.json")
    seed_finance_patterns(store)
    # Add one AutoDream-detected pattern at freq=3 (above default threshold)
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
    # And one low-frequency user pattern (freq=1, would normally be hidden)
    data["patterns"]["user_detected:once_off"] = {
        "pattern_id": "user_detected:once_off",
        "description": "observed only once",
        "tool_sequence": ["sql_query"],
        "frequency": 1,
        "estimated_time_saved_minutes": 10,
        "required_connections": [],
        "first_seen": now,
        "last_seen": now,
        "sessions": ["s1"],
        "suppressed": False,
        "suppressed_until": None,
    }
    store.save(data)
    return store


async def test_seeds_surface_despite_frequency_filter(seeded_store):
    """The 6 finance seeds (freq=1) must appear alongside the 1
    frequency-qualifying user pattern. The freq=1 non-seed user
    pattern must still be filtered out."""
    tool = SuggestAutomationTool(store=seeded_store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    result = await tool.execute(SuggestAutomationInput(), ctx)
    assert not result.is_error
    suggestions = result.content["suggestions"]
    ids = [s["pattern_id"] for s in suggestions]

    # All 6 seeds are present
    for seed_id in (
        "finance_seed:monthly_close",
        "finance_seed:quarterly_budget_review",
        "finance_seed:recurring_aging_report",
        "finance_seed:cash_flow_forecast",
        "finance_seed:expense_reimbursement_review",
        "finance_seed:year_end_close",
    ):
        assert seed_id in ids, f"missing seed {seed_id}"

    # The qualifying user pattern (freq=3) is also present
    assert "user_detected:weekly_rollup" in ids
    # The below-threshold user pattern is filtered out
    assert "user_detected:once_off" not in ids


async def test_seeds_carry_is_seed_flag(seeded_store):
    """Output marks seeds so the LLM can narrate honestly without
    pretending they were observed."""
    tool = SuggestAutomationTool(store=seeded_store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    result = await tool.execute(SuggestAutomationInput(), ctx)
    by_id = {s["pattern_id"]: s for s in result.content["suggestions"]}
    assert by_id["finance_seed:monthly_close"]["is_seed"] is True
    assert by_id["user_detected:weekly_rollup"]["is_seed"] is False


async def test_summary_distinguishes_seeds_from_detected(seeded_store):
    """Summary text should explicitly separate ``baseline rituals``
    (seeds) from ``detected patterns`` (AutoDream) so the LLM
    narrates the semantic difference rather than smashing them into
    one count."""
    tool = SuggestAutomationTool(store=seeded_store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    result = await tool.execute(SuggestAutomationInput(), ctx)
    summary = result.content["summary"]
    low = summary.lower()
    assert "6" in summary or "six" in low  # 6 seeds surfaced
    # Either word set distinguishes seeds from detected
    assert "seed" in low or "baseline" in low or "ritual" in low
    assert "detected" in low or "observed" in low or "from your" in low


async def test_seeds_suppressible_via_dismiss(seeded_store):
    """The ``dismiss=`` shortcut works on seeds too — user can
    permanently hide seeds they don't care about (e.g. an AR-less
    company hides finance_seed:recurring_aging_report)."""
    tool = SuggestAutomationTool(store=seeded_store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    # Dismiss a seed
    r1 = await tool.execute(
        SuggestAutomationInput(dismiss="finance_seed:recurring_aging_report"),
        ctx,
    )
    assert not r1.is_error
    assert r1.content == {"dismissed": "finance_seed:recurring_aging_report", "ok": True}

    # Next listing omits the dismissed seed
    r2 = await tool.execute(SuggestAutomationInput(), ctx)
    ids = [s["pattern_id"] for s in r2.content["suggestions"]]
    assert "finance_seed:recurring_aging_report" not in ids
    # Other seeds still present
    assert "finance_seed:monthly_close" in ids


async def test_empty_store_returns_honest_empty_message(tmp_path):
    """No seeds, no detected patterns → summary must be honest about
    it (not accidentally claim "N rituals" when N=0)."""
    store = PatternStore(path=tmp_path / "patterns.json")
    tool = SuggestAutomationTool(store=store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    result = await tool.execute(SuggestAutomationInput(), ctx)
    assert not result.is_error
    assert result.content["suggestions"] == []
    # Summary acknowledges nothing found
    assert result.content["summary"]
    assert "no" in result.content["summary"].lower() or \
           "empty" in result.content["summary"].lower()


async def test_min_frequency_override_still_works_for_non_seeds(seeded_store):
    """Explicit min_frequency=1 should include the freq=1 user pattern
    too — seeds bypass the threshold, but the threshold itself still
    applies to non-seed entries when the caller asks for it."""
    tool = SuggestAutomationTool(store=seeded_store)
    from yigthinker.session import SessionContext
    ctx = SessionContext()

    result = await tool.execute(
        SuggestAutomationInput(min_frequency=1),
        ctx,
    )
    ids = [s["pattern_id"] for s in result.content["suggestions"]]
    # Now the freq=1 user pattern IS included
    assert "user_detected:once_off" in ids
