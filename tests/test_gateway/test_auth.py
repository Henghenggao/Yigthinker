"""Tests for gateway authentication."""
from pathlib import Path

from yigthinker.gateway.auth import GatewayAuth


def test_creates_token_file(tmp_path):
    token_path = tmp_path / "gateway.token"
    auth = GatewayAuth(token_path=token_path)

    assert token_path.exists()
    assert len(auth.token) == 64  # 32 bytes hex
    assert auth.verify(auth.token)


def test_loads_existing_token(tmp_path):
    token_path = tmp_path / "gateway.token"
    token_path.write_text("deadbeef" * 8, encoding="utf-8")

    auth = GatewayAuth(token_path=token_path)
    assert auth.token == "deadbeef" * 8


def test_verify_rejects_bad_token(tmp_path):
    auth = GatewayAuth(token_path=tmp_path / "gateway.token")
    assert not auth.verify("wrong_token")
    assert not auth.verify("")


def test_token_persistence(tmp_path):
    token_path = tmp_path / "gateway.token"
    auth1 = GatewayAuth(token_path=token_path)
    auth2 = GatewayAuth(token_path=token_path)
    assert auth1.token == auth2.token
