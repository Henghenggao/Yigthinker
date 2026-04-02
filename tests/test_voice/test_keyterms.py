from __future__ import annotations
from yigthinker.voice.keyterms import FINANCIAL_KEYTERMS, build_keyterm_list


def test_financial_keyterms_not_empty():
    assert len(FINANCIAL_KEYTERMS) > 10


def test_keyterms_contain_chinese_financial_terms():
    assert "应收账款" in FINANCIAL_KEYTERMS
    assert "应付账款" in FINANCIAL_KEYTERMS


def test_keyterms_contain_english_financial_terms():
    assert "EBITDA" in FINANCIAL_KEYTERMS
    assert "accounts receivable" in FINANCIAL_KEYTERMS


def test_build_keyterm_list_includes_custom():
    custom = ["custom_term_xyz", "another_term"]
    result = build_keyterm_list(custom_terms=custom)
    assert "custom_term_xyz" in result
    assert "应收账款" in result  # built-in included


def test_build_keyterm_list_deduplicates():
    custom = ["应收账款", "EBITDA"]  # already in built-ins
    result = build_keyterm_list(custom_terms=custom)
    assert result.count("应收账款") == 1
