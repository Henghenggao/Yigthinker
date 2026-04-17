"""HMAC-SHA256 signature verification for Microsoft Teams outgoing webhooks."""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod

from fastapi import HTTPException, Request


def verify_teams_hmac_signature(raw_body: bytes, auth_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from Teams outgoing webhook.

    Args:
        raw_body: Raw request bytes (NOT re-serialized JSON).
        auth_header: Full Authorization header value (e.g. "HMAC abc123==").
        secret: Base64-encoded security token from Teams.

    Returns:
        True if signature is valid.
    """
    if not auth_header.startswith("HMAC "):
        return False
    provided = auth_header[5:]
    key_bytes = base64.b64decode(secret)
    computed = hmac_mod.new(key_bytes, raw_body, hashlib.sha256)
    expected = base64.b64encode(computed.digest()).decode("utf-8")
    return hmac_mod.compare_digest(expected, provided)


async def require_teams_hmac(request: Request, secret: str) -> bytes:
    """FastAPI dependency that verifies Teams HMAC and returns raw body.

    Raises HTTPException(401) on failure. Must be called BEFORE any JSON parsing
    to ensure raw_body bytes match what Teams signed.
    """
    raw_body = await request.body()
    auth_header = request.headers.get("Authorization", "")
    if not verify_teams_hmac_signature(raw_body, auth_header, secret):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")
    return raw_body
