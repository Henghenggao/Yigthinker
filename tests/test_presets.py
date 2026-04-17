"""Preset data pack inventory test.

Data pack is dormant — only verifies files exist and parse as JSON.
No loader / schema enforcement in Phase 1a (per ADR-008).
"""
from __future__ import annotations

import json
from pathlib import Path

PRESETS_DIR = Path(__file__).parent.parent / "yigthinker" / "presets"


def test_persona_dir_exists_and_nonempty():
    d = PRESETS_DIR / "personas"
    assert d.is_dir()
    files = list(d.glob("*.json"))
    assert len(files) >= 16   # Phase 1a spec floor; actual is 25+


def test_team_dir_exists_and_nonempty():
    d = PRESETS_DIR / "teams"
    assert d.is_dir()
    files = list(d.glob("*.json"))
    assert len(files) >= 2


def test_all_persona_jsons_parse():
    d = PRESETS_DIR / "personas"
    for f in d.glob("*.json"):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{f.name} is not valid JSON: {exc}") from exc


def test_all_team_jsons_parse():
    d = PRESETS_DIR / "teams"
    for f in d.glob("*.json"):
        json.loads(f.read_text(encoding="utf-8"))
