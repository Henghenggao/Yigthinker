"""Yigfinance Track D: canonical finance workflow patterns pre-seeded into
PatternStore so `suggest_automation` has meaningful suggestions on day one.

ADR-011 (Yigfinance as first-class skill layer) commits to 6 canonical
finance rituals: monthly close, quarterly budget review, AR aging,
cash flow forecast, expense reimbursement, year-end close. Without these,
a fresh `pip install yigthinker` user sees zero automation suggestions
until AutoDream has accumulated several sessions of cross-session data —
the architect-not-executor value prop is invisible for days.

Design contract:

- Pattern IDs are prefixed ``finance_seed:`` so downstream readers can
  distinguish seeded rituals from AutoDream-detected patterns.
- `seed_finance_patterns(store)` is idempotent: re-running it on a store
  that already has seeds adds zero new entries, never overwrites
  existing ones, and preserves any user suppressions.
- Build-app calls this unconditionally on every boot — safe by the
  idempotency contract above.

The seeds compose existing tools (``sql_query``, ``df_transform``, etc.)
into ritual sequences. They intentionally do NOT reference Yigfinance's
own slash commands (``/close`` etc.) because suggest_automation surfaces
``tool_sequence`` to the LLM for context, and commands are a thinner
shell over the same tools.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from yigthinker.memory.patterns import PatternStore


# ---------------------------------------------------------------------------
# The 6 canonical finance ritual patterns (ADR-011 §Track D)
# ---------------------------------------------------------------------------
#
# Schema matches PatternStore's D-18 contract. ``first_seen`` / ``last_seen``
# are filled in at load time so multiple installs don't share a forged
# timestamp history. ``sessions`` is empty — these are seeds, not patterns
# detected from real user activity; incrementing ``frequency`` on match is
# AutoDream's job, not ours.

FINANCE_SEEDS: dict[str, dict[str, Any]] = {
    "finance_seed:monthly_close": {
        "pattern_id": "finance_seed:monthly_close",
        "description": (
            "Monthly close ritual: reconcile journal entries, produce P&L + "
            "balance sheet + cash flow statement, compute variance vs budget, "
            "export formatted xlsx and chart. Typically runs on the first "
            "business day of each month against the prior period."
        ),
        "tool_sequence": [
            "sql_query",
            "df_merge",
            "df_transform",
            "finance_analyze",
            "report_generate",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 180,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
    "finance_seed:quarterly_budget_review": {
        "pattern_id": "finance_seed:quarterly_budget_review",
        "description": (
            "Quarterly budget vs actual review across cost centers: pull "
            "period actuals and planned budget, compute variance, flag "
            "items exceeding threshold, produce CFO-ready variance "
            "waterfall chart + commentary. Runs on the first week of each "
            "new quarter."
        ),
        "tool_sequence": [
            "sql_query",
            "finance_analyze",
            "chart_create",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 120,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
    "finance_seed:recurring_aging_report": {
        "pattern_id": "finance_seed:recurring_aging_report",
        "description": (
            "Accounts receivable aging report: bucket open invoices into "
            "0-30 / 31-60 / 61-90 / 90+ day tranches, drill down on the "
            "biggest 90+ accounts, produce an xlsx with a bucketed summary "
            "chart. Common weekly or biweekly AR team ritual."
        ),
        "tool_sequence": [
            "sql_query",
            "df_transform",
            "finance_analyze",
            "chart_create",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 45,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
    "finance_seed:cash_flow_forecast": {
        "pattern_id": "finance_seed:cash_flow_forecast",
        "description": (
            "13-week cash flow forecast: pull AR and AP schedules, project "
            "collections and disbursements, produce a weekly waterfall "
            "chart and running-balance table. Rolling weekly cadence for "
            "treasury teams."
        ),
        "tool_sequence": [
            "sql_query",
            "df_merge",
            "forecast_timeseries",
            "chart_create",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 90,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
    "finance_seed:expense_reimbursement_review": {
        "pattern_id": "finance_seed:expense_reimbursement_review",
        "description": (
            "Expense reimbursement review: load pending expense claims, "
            "validate against policy, flag outliers (amount / category / "
            "frequency), produce an approval-ready xlsx. Weekly AP ritual."
        ),
        "tool_sequence": [
            "sql_query",
            "finance_validate",
            "df_transform",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 60,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
    "finance_seed:year_end_close": {
        "pattern_id": "finance_seed:year_end_close",
        "description": (
            "Year-end close ritual: consolidate all twelve monthly closes, "
            "produce annual P&L / balance sheet / cash flow, prepare tax "
            "packet, build audit trail workbook. Runs once per fiscal year "
            "— high value to pre-register so suggest_automation surfaces "
            "it to the LLM when December analysis patterns appear."
        ),
        "tool_sequence": [
            "sql_query",
            "df_merge",
            "finance_analyze",
            "finance_validate",
            "report_generate",
            "excel_write",
        ],
        "frequency": 1,
        "estimated_time_saved_minutes": 480,
        "required_connections": ["finance"],
        "sessions": [],
        "suppressed": False,
        "suppressed_until": None,
    },
}


# ---------------------------------------------------------------------------
# Idempotent loader
# ---------------------------------------------------------------------------

def seed_finance_patterns(store: PatternStore) -> int:
    """Load the 6 canonical finance patterns into ``store``.

    Idempotent: returns the count of patterns newly added (0 on
    subsequent runs). Existing patterns — including user suppressions —
    are preserved untouched. Safe to call on every ``build_app`` boot.

    Implementation notes:
    - Read current store state
    - For each seed whose pattern_id is NOT present, inject it with
      fresh ``first_seen`` / ``last_seen`` timestamps
    - If anything was added, persist via ``store.save``
    - Never modify existing entries, even if a seed's static definition
      has changed between versions. Upgrading a stale seed is a
      conscious decision the user can trigger by deleting the entry
      and re-running.
    """
    data = store.load()
    patterns: dict[str, dict[str, Any]] = data.setdefault("patterns", {})
    now = datetime.now(timezone.utc).isoformat()

    added = 0
    for pattern_id, seed in FINANCE_SEEDS.items():
        if pattern_id in patterns:
            continue
        # Deep-copy the seed so later mutations to the in-memory dict
        # don't leak back into our module-level FINANCE_SEEDS constant.
        entry = {**seed}
        entry["first_seen"] = now
        entry["last_seen"] = now
        patterns[pattern_id] = entry
        added += 1

    if added:
        store.save(data)
    return added
