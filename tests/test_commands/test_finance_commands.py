"""Yigfinance Track A: finance slash commands loaded and exposed to the LLM.

ADR-011 Track A ships 5 finance commands under
``yigthinker/commands/finance/*.md`` (``/ar-aging`` first, per the
vertical-slice-1 plan). Each file is an LLM-facing recipe following the
same frontmatter contract as ``yigthinker/commands/advisor.md`` and
plugin-supplied commands (see ``yigthinker/plugins/command.py``).

Integration layer (this test suite):
1. ``yigthinker/commands/finance/`` directory exists and is discoverable.
2. A helper ``load_builtin_finance_commands()`` reads the directory and
   returns parsed ``SlashCommand`` objects.
3. ``ContextManager.build_finance_commands_directive(commands)`` produces
   a system-prompt section listing each command with its description —
   wired into agent.py's prompt assembly next to the existing directives.
4. AR-aging recipe is the first concrete command — the rest of Track A
   (close / variance / recon / budget-var) follows the same template.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yigthinker.context_manager import ContextManager
from yigthinker.plugins.command import SlashCommand


# ---------------------------------------------------------------------------
# Directory + loader contract
# ---------------------------------------------------------------------------

def test_finance_commands_dir_exists():
    """The directory that holds finance command recipes must exist so the
    loader has something to scan. Presence alone is the contract — empty
    dir is fine (other tracks populate the files)."""
    pkg = Path(__file__).resolve().parent.parent.parent
    finance_dir = pkg / "yigthinker" / "commands" / "finance"
    assert finance_dir.exists(), (
        f"Expected finance commands dir at {finance_dir}; create it with "
        f"at minimum ar-aging.md (Track A2 first slice)"
    )
    assert finance_dir.is_dir()


def test_ar_aging_md_exists_with_valid_frontmatter():
    """Track A2: ``ar-aging.md`` is the first-vertical-slice command and
    must be present with a description, argument-hint, and non-empty
    body (the LLM's recipe)."""
    pkg = Path(__file__).resolve().parent.parent.parent
    md = pkg / "yigthinker" / "commands" / "finance" / "ar-aging.md"
    assert md.exists(), f"Missing {md}"
    text = md.read_text(encoding="utf-8")
    assert text.startswith("---"), "Expected YAML frontmatter"
    assert "description:" in text
    # Body must be non-trivial — it's the recipe the LLM follows
    body_after_frontmatter = text.split("---", 2)[-1].strip()
    assert len(body_after_frontmatter) > 200, (
        "Recipe body is too short — the LLM needs enough context to "
        "execute the aging workflow (expected > 200 chars)"
    )


def test_load_builtin_finance_commands_returns_parsed_commands():
    from yigthinker.commands.finance import load_builtin_finance_commands
    commands = load_builtin_finance_commands()
    names = {cmd.name for cmd in commands}
    assert "ar-aging" in names
    ar_aging = next(c for c in commands if c.name == "ar-aging")
    assert ar_aging.description
    # Recipe body must reference the generic tools the LLM will call
    assert "sql_query" in ar_aging.body or "excel_write" in ar_aging.body


def test_load_is_stable_and_idempotent():
    """Calling the loader twice returns the same set (no caching
    bugs)."""
    from yigthinker.commands.finance import load_builtin_finance_commands
    a = {c.name for c in load_builtin_finance_commands()}
    b = {c.name for c in load_builtin_finance_commands()}
    assert a == b


# ---------------------------------------------------------------------------
# ContextManager directive — system prompt injection
# ---------------------------------------------------------------------------

def test_build_finance_commands_directive_lists_each_command():
    cm = ContextManager()
    commands = [
        SlashCommand(
            name="ar-aging",
            description="Bucket AR by age and flag 90+ accounts",
            argument_hint="[as-of-date]",
            body="recipe body here",
        ),
        SlashCommand(
            name="close",
            description="Monthly close",
            body="recipe body",
        ),
    ]
    directive = cm.build_finance_commands_directive(commands)
    assert directive is not None
    assert "/ar-aging" in directive
    assert "/close" in directive
    # Descriptions appear so the LLM can reason about when to use them
    assert "Bucket AR by age" in directive
    assert "Monthly close" in directive


def test_build_finance_commands_directive_none_for_empty_list():
    """No commands discovered → no directive (keep system prompt lean)."""
    cm = ContextManager()
    assert cm.build_finance_commands_directive([]) is None


def test_build_finance_commands_directive_mentions_recipe_contract():
    """The directive must tell the LLM that typing the slash command
    means: load the recipe, execute step by step, trigger
    suggest_automation at the end — otherwise the LLM won't know
    slash commands are anything special."""
    cm = ContextManager()
    commands = [
        SlashCommand(
            name="ar-aging",
            description="AR aging report",
            body="recipe",
        ),
    ]
    directive = cm.build_finance_commands_directive(commands)
    assert directive is not None
    # The behavioral contract must be stated explicitly:
    assert "suggest_automation" in directive
    # And the LLM must be told these aren't ordinary free-form prompts
    lower = directive.lower()
    assert "follow" in lower or "execute" in lower or "recipe" in lower
