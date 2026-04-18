"""Yigfinance built-in slash commands (ADR-011 Track A).

Each ``.md`` file in this directory is a recipe the LLM follows when
the user invokes the corresponding slash command (``/ar-aging``,
``/close``, etc.). Frontmatter contract matches
``yigthinker/plugins/command.py``'s ``SlashCommand`` + plugin-supplied
commands so downstream UIs (TUI auto-complete, Teams command parser)
can treat built-in and plugin commands uniformly.
"""
from __future__ import annotations

from pathlib import Path

from yigthinker.plugins.command import SlashCommand, load_commands_from_dir


def load_builtin_finance_commands() -> list[SlashCommand]:
    """Discover + parse every ``.md`` recipe in this package directory.

    Returns the recipes in alphabetical order (matches
    ``load_commands_from_dir``'s sorted glob). Safe to call repeatedly —
    each call reads the filesystem fresh, so edits to recipe files
    without a process restart are reflected on next call.
    """
    here = Path(__file__).resolve().parent
    return load_commands_from_dir(here)
