"""Strip markdown tables from the LLM text when a native table card renders.

2026-04-18 UAT finding: after `sql_query` returns a DataFrame, the Teams
adapter composes an Adaptive Card with a native `Table` block AND appends
the LLM's final prose (which includes the same data as a markdown table).
Adaptive Cards v1.5 do NOT render markdown tables — pipe-delimited rows
come through as raw `|` characters, creating visual garbage right next
to the clean native table.

Fix: when the card already contains a native `Table` element, strip
markdown-table syntax from the appended text so the narrative prose is
kept but the duplicate table is removed.

Chart artifacts have the same symptom — the LLM often restates data that
the chart already encodes. Same strip applies.

Plain text without a markdown table is unchanged in all cases.
"""
from __future__ import annotations

import pytest

from yigthinker.presence.channels.teams.adapter import _strip_markdown_tables


# ---------------------------------------------------------------------------
# Pure function: _strip_markdown_tables
# ---------------------------------------------------------------------------

def test_strip_removes_simple_markdown_table():
    text = (
        "Here is the data:\n\n"
        "| col1 | col2 |\n"
        "|------|------|\n"
        "| a    | 1    |\n"
        "| b    | 2    |\n\n"
        "That's the top 2 rows."
    )
    stripped = _strip_markdown_tables(text)
    assert "| col1 | col2 |" not in stripped
    assert "|------" not in stripped
    assert "| a    | 1" not in stripped
    # Narrative prose is preserved
    assert "Here is the data:" in stripped
    assert "That's the top 2 rows." in stripped


def test_strip_handles_windows_style_crlf():
    """Tables authored with CRLF (Windows / Teams copy-paste) must also strip."""
    text = "Intro\r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\nOutro"
    stripped = _strip_markdown_tables(text)
    assert "|" not in stripped or "| a | b |" not in stripped
    assert "Intro" in stripped
    assert "Outro" in stripped


def test_strip_removes_inline_single_line_pipe_dump():
    """UAT reproducer: LLM sometimes renders a whole table on one line after
    Teams collapses newlines (e.g. '| Rank | Region | ... | 1 | Americas ...')
    — this variant must also be caught and stripped."""
    text = (
        "Top rows summary.\n"
        "| Rank | Region | Quarter | Year | Amount (EUR) | |------|---------|---------|"
        "------|--------------| | 1 | Americas | Q2 | 2026 | 2,590,000 |\n"
        "Observations: Americas dominates."
    )
    stripped = _strip_markdown_tables(text)
    assert "|------" not in stripped
    assert "| 1 | Americas" not in stripped
    assert "Top rows summary." in stripped
    assert "Observations: Americas dominates." in stripped


def test_strip_preserves_text_without_tables():
    """Pure prose must pass through unchanged."""
    text = "The NPV is $17.63 at 8%, positive and worth pursuing."
    assert _strip_markdown_tables(text) == text


def test_strip_preserves_inline_code_with_pipes():
    """Inline code that happens to contain pipes (e.g. regex, shell) must
    NOT be mistaken for a table."""
    text = "Run this: `grep 'foo\\|bar' file.txt` — filters for either."
    stripped = _strip_markdown_tables(text)
    assert "grep" in stripped
    assert "foo\\|bar" in stripped


def test_strip_preserves_blockquote_and_lists():
    """Markdown bullets and blockquotes (no pipes) must survive."""
    text = (
        "Steps:\n"
        "- Load data\n"
        "- Query\n"
        "- Report\n\n"
        "> Key insight: EMEA is growing."
    )
    assert _strip_markdown_tables(text) == text


def test_strip_collapses_only_blank_lines_it_created():
    """After stripping a table, we should not leave more than 2 consecutive
    blank lines in a row — keep the output tidy."""
    text = (
        "Intro.\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "Outro."
    )
    stripped = _strip_markdown_tables(text)
    assert "\n\n\n" not in stripped
    assert "Intro." in stripped
    assert "Outro." in stripped


# ---------------------------------------------------------------------------
# Integration: markdown tables stripped only when a native artifact renders
# ---------------------------------------------------------------------------

def test_append_text_to_card_strips_markdown_when_native_table_present():
    """End-to-end: a Table-containing card appended with text containing
    a markdown table must end up with the native Table + stripped narrative."""
    from yigthinker.presence.channels.teams.adapter import TeamsAdapter
    # Construct a minimal adapter instance using its class constants
    cfg = {"client_id": "x", "tenant_id": "y", "client_secret": "z"}
    adapter = TeamsAdapter(cfg)

    card_with_table = {
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": "Data Preview"},
            {"type": "Table", "rows": [{"cells": [{"items": [{"text": "hdr"}]}]}]},
        ],
    }
    text = (
        "Here is the data:\n\n"
        "| col | val |\n|-----|-----|\n| a | 1 |\n\n"
        "Americas dominates."
    )
    result = adapter._append_text_to_card(card_with_table, text)

    # Find the appended TextBlock (last element)
    appended = result["body"][-1]
    assert appended["type"] == "TextBlock"
    assert "| col | val |" not in appended["text"]
    assert "Here is the data:" in appended["text"]
    assert "Americas dominates." in appended["text"]


def test_append_text_to_card_strips_markdown_always_in_teams():
    """2026-04-18 UAT follow-up: an earlier iteration of this test preserved
    markdown tables when the card had no native Table element, on the theory
    that the LLM's markdown might be the intended output. That was wrong for
    Teams specifically — Adaptive Cards v1.5 do NOT render markdown tables
    under any circumstance, so a pipe-delimited table always renders as
    literal `|` characters and always looks like a bug to the user.

    Policy: Teams `_append_text_to_card` strips markdown tables
    UNCONDITIONALLY. Other channels (Feishu, GChat) get their own policy
    via their own adapters."""
    from yigthinker.presence.channels.teams.adapter import TeamsAdapter
    cfg = {"client_id": "x", "tenant_id": "y", "client_secret": "z"}
    adapter = TeamsAdapter(cfg)

    # File card (no native Table, just a download action) — the scenario
    # where the UAT exposed the gap: xlsx delivered cleanly but the LLM
    # also wrote a markdown table describing the same data.
    card_file = {
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": "Saved total_revenue_by_region.xlsx"},
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "Download", "url": "https://x/dl"},
        ],
    }
    text = (
        "Done! Generated total_revenue_by_region.xlsx with three regions:\n\n"
        "| Region | Total Revenue (EUR) |\n"
        "|---|---|\n"
        "| Americas | 13,800,000 |\n"
        "| EMEA | 8,260,000 |\n"
        "| APAC | 6,280,000 |\n\n"
        "Frozen header row included."
    )
    result = adapter._append_text_to_card(card_file, text)

    appended = result["body"][-1]
    # Markdown table must be gone even without a native Table element:
    assert "| Region | Total Revenue" not in appended["text"]
    assert "| Americas | 13,800,000 |" not in appended["text"]
    assert "|---|---|" not in appended["text"]
    # Narrative prose survives:
    assert "Generated total_revenue_by_region.xlsx" in appended["text"]
    assert "Frozen header row included." in appended["text"]


def test_append_text_to_card_still_preserves_pure_prose():
    """Sanity: prose without any pipe-table syntax must pass through
    unchanged regardless of card shape."""
    from yigthinker.presence.channels.teams.adapter import TeamsAdapter
    cfg = {"client_id": "x", "tenant_id": "y", "client_secret": "z"}
    adapter = TeamsAdapter(cfg)

    card_plain = {"type": "AdaptiveCard", "version": "1.5", "body": []}
    text = "The NPV is $17.63, which is positive and worth pursuing."
    result = adapter._append_text_to_card(card_plain, text)
    assert result["body"][-1]["text"] == text
