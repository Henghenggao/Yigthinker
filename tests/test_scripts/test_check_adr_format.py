from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_adr_format import AdrViolation, check_file


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


GOOD_HEAD = "# ADR-001: Test\n\nStatus: Accepted  |  Date: 2026-04-17  |  Supersedes: —\nLang: en\n"
SECTIONS = "\n## Context\nctx\n\n## Decision\ndec\n\n## Consequences\n- a\n\n## References\n- r\n"


def test_english_wordcount_under_limit_passes(tmp_path):
    body = GOOD_HEAD + SECTIONS + "\n" + (" word" * 100)
    path = _write(tmp_path, "001-ok.md", body)
    assert check_file(path) == []


def test_english_wordcount_over_limit_fails(tmp_path):
    body = GOOD_HEAD + SECTIONS + "\n" + ("word " * 600)
    path = _write(tmp_path, "001-long.md", body)
    violations = check_file(path)
    assert any(v.code == "WORD_LIMIT" for v in violations)


def test_chinese_charcount_over_limit_fails(tmp_path):
    head = GOOD_HEAD.replace("Lang: en", "Lang: zh")
    body = head + SECTIONS + ("啊" * 800)
    path = _write(tmp_path, "001-zh.md", body)
    violations = check_file(path)
    assert any(v.code == "CHAR_LIMIT" for v in violations)


def test_missing_section_fails(tmp_path):
    body = GOOD_HEAD + "\n## Context\nctx\n\n## Decision\ndec\n"
    path = _write(tmp_path, "001-miss.md", body)
    violations = check_file(path)
    codes = {v.code for v in violations}
    assert "MISSING_SECTION" in codes


def test_default_lang_is_zh(tmp_path):
    # No Lang: line — default to zh; 800 chars fails
    head = "# ADR-001: Test\n\nStatus: Accepted  |  Date: 2026-04-17  |  Supersedes: —\n"
    body = head + SECTIONS + ("啊" * 800)
    path = _write(tmp_path, "001-default.md", body)
    violations = check_file(path)
    assert any(v.code == "CHAR_LIMIT" for v in violations)


def test_code_blocks_excluded_from_count(tmp_path):
    head = GOOD_HEAD.replace("Lang: en", "Lang: zh")
    # 400 CJK chars outside code fence + 1000 inside — inside must not count
    code_block = "\n```python\n" + ("x " * 1000) + "\n```\n"
    body = head + SECTIONS + ("啊" * 400) + code_block
    path = _write(tmp_path, "001-code.md", body)
    assert check_file(path) == []
