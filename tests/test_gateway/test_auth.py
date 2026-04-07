"""Tests for gateway authentication."""
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def test_windows_uses_icacls(tmp_path):
    """On Windows, _load_or_create uses icacls instead of chmod."""
    token_path = tmp_path / "gateway.token"
    with patch("yigthinker.gateway.auth.sys") as mock_sys, \
         patch("yigthinker.gateway.auth.subprocess") as mock_subprocess:
        mock_sys.platform = "win32"
        mock_subprocess.run = MagicMock()
        auth = GatewayAuth(token_path=token_path)
    mock_subprocess.run.assert_called_once()
    args = mock_subprocess.run.call_args
    assert args[0][0][0] == "icacls"
