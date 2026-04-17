"""Tests for gateway session key derivation and parsing."""
import pytest

from yigthinker.presence.gateway.session_key import SessionKey


def test_per_sender():
    key = SessionKey.per_sender("feishu", "ou_abc123")
    assert key == "feishu:ou_abc123"


def test_per_channel():
    key = SessionKey.per_channel("feishu", "oc_xyz789")
    assert key == "feishu:chat:oc_xyz789"


def test_named():
    key = SessionKey.named("tui", "user1", "q1-analysis")
    assert key == "tui:user1:q1-analysis"


def test_global():
    assert SessionKey.global_key() == "global"


def test_parse_per_sender():
    parsed = SessionKey.parse("feishu:ou_abc123")
    assert parsed["scope"] == "per-sender"
    assert parsed["channel"] == "feishu"
    assert parsed["sender_id"] == "ou_abc123"


def test_parse_per_channel():
    parsed = SessionKey.parse("feishu:chat:oc_xyz789")
    assert parsed["scope"] == "per-channel"
    assert parsed["channel"] == "feishu"
    assert parsed["chat_id"] == "oc_xyz789"


def test_parse_named():
    parsed = SessionKey.parse("tui:user1:q1-analysis")
    assert parsed["scope"] == "named"
    assert parsed["channel"] == "tui"
    assert parsed["sender_id"] == "user1"
    assert parsed["label"] == "q1-analysis"


def test_parse_global():
    parsed = SessionKey.parse("global")
    assert parsed["scope"] == "global"


def test_parse_invalid():
    with pytest.raises(ValueError):
        SessionKey.parse("a:b:c:d:e")


def test_invalid_segment_raises():
    with pytest.raises(ValueError):
        SessionKey.per_sender("feishu", "bad segment with spaces")


def test_empty_segment_raises():
    with pytest.raises(ValueError):
        SessionKey.per_sender("", "user1")


def test_from_config_per_sender():
    key = SessionKey.from_config("per-sender", "feishu", sender_id="ou_abc")
    assert key == "feishu:ou_abc"


def test_from_config_per_channel():
    key = SessionKey.from_config("per-channel", "teams", chat_id="ch_123")
    assert key == "teams:chat:ch_123"


def test_from_config_named():
    key = SessionKey.from_config("named", "tui", sender_id="user1", label="project-x")
    assert key == "tui:user1:project-x"


def test_from_config_global():
    key = SessionKey.from_config("global", "any")
    assert key == "global"
