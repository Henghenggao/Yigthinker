"""Tests for Teams HMAC-SHA256 signature verification (TEAMS-01)."""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod

from yigthinker.channels.teams.hmac import verify_teams_hmac_signature


def _compute_hmac(body: bytes, secret_b64: str) -> str:
    """Helper: compute HMAC-SHA256 the same way Teams does."""
    key = base64.b64decode(secret_b64)
    h = hmac_mod.new(key, body, hashlib.sha256)
    return base64.b64encode(h.digest()).decode()


# Use a known secret for all tests
_SECRET_B64 = base64.b64encode(b"test-webhook-secret-key-1234").decode()
_BODY = b'{"text": "hello", "from": {"aadObjectId": "user-1"}}'


def test_valid_hmac_returns_true():
    sig = _compute_hmac(_BODY, _SECRET_B64)
    auth = f"HMAC {sig}"
    assert verify_teams_hmac_signature(_BODY, auth, _SECRET_B64) is True


def test_invalid_hmac_returns_false():
    auth = "HMAC dGhpcyBpcyBub3QgYSB2YWxpZCBzaWduYXR1cmU="
    assert verify_teams_hmac_signature(_BODY, auth, _SECRET_B64) is False


def test_missing_hmac_prefix_returns_false():
    sig = _compute_hmac(_BODY, _SECRET_B64)
    auth = f"Bearer {sig}"
    assert verify_teams_hmac_signature(_BODY, auth, _SECRET_B64) is False


def test_empty_auth_header_returns_false():
    assert verify_teams_hmac_signature(_BODY, "", _SECRET_B64) is False


def test_tampered_body_returns_false():
    sig = _compute_hmac(_BODY, _SECRET_B64)
    auth = f"HMAC {sig}"
    tampered = b'{"text": "HACKED", "from": {"aadObjectId": "user-1"}}'
    assert verify_teams_hmac_signature(tampered, auth, _SECRET_B64) is False
