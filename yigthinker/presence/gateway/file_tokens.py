"""HMAC-signed short-lived file tokens for outbound artifact delivery.

Background: Teams Adaptive Cards render ``Action.OpenUrl`` buttons that the
Teams client opens in the user's browser — without bearer auth headers. We
need a capability-token delivery mechanism where the token itself is the
authorization (same shape as the existing chart-image serving at
``/api/charts/{chart_id}``).

Design (see ``.planning/quick/260416-kyn-.../260416-kyn-RESEARCH.md``
§"Primary Recommendation"):

- Each token is ``<nonce>.<sig24>`` where ``nonce`` is 16 bytes of
  ``secrets.token_urlsafe`` and ``sig24`` is the first 24 hex chars of
  HMAC-SHA256 over ``nonce:path:expiry`` with the server secret.
- The store keeps an in-memory dict (token → (path, expiry_monotonic))
  guarded by ``threading.Lock`` — mirrors VarRegistry's pattern.
- TTL defaults to 30 minutes. Plenty for a user to click "Download" in
  Teams; short enough that a leaked token is not a long-lived credential.
- ``resolve()`` re-verifies the HMAC against the stored tuple before
  returning the path. In-process tampering is implausible but cheap to
  guard against and forces hmac.compare_digest for timing safety.
- The stored ``Path`` is always absolute (enforced at ``issue()``).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path

DEFAULT_FILE_TOKEN_TTL_SECONDS: int = 30 * 60  # 30 minutes


def _sign(secret: bytes, nonce: str, path: Path, expiry: float) -> str:
    payload = f"{nonce}:{str(path)}:{expiry}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:24]


class FileTokenStore:
    """Issue and resolve HMAC-signed file tokens with per-token TTL.

    The store is deliberately simple and in-process: gateway restart
    invalidates all outstanding tokens, and that is the intended behavior
    (tokens are a per-boot capability). For multi-worker deployments the
    store would need a shared backend; the current gateway is single-
    worker (FastAPI + uvicorn workers=1).
    """

    def __init__(
        self,
        secret: bytes,
        ttl_seconds: int = DEFAULT_FILE_TOKEN_TTL_SECONDS,
    ) -> None:
        if not secret:
            raise ValueError("FileTokenStore secret must be non-empty")
        if ttl_seconds <= 0:
            raise ValueError("FileTokenStore ttl_seconds must be positive")
        self._secret: bytes = secret
        self._ttl_seconds: int = int(ttl_seconds)
        self._entries: dict[str, tuple[Path, float]] = {}
        self._lock = threading.Lock()

    def issue(self, path: Path) -> str:
        if not path.is_absolute():
            raise ValueError(
                f"FileTokenStore.issue requires an absolute path, got {path!r}"
            )
        nonce = secrets.token_urlsafe(16)
        expiry = time.monotonic() + self._ttl_seconds
        sig = _sign(self._secret, nonce, path, expiry)
        token = f"{nonce}.{sig}"
        with self._lock:
            self._entries[token] = (path, expiry)
            self._sweep_expired_locked()
        return token

    def resolve(self, token: str) -> Path | None:
        if not token or "." not in token:
            return None
        nonce, _, _sig = token.partition(".")
        if not nonce or not _sig:
            return None

        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            path, expiry = entry
            if expiry <= time.monotonic():
                # Expired — drop and return None.
                self._entries.pop(token, None)
                return None

            # Defensive: recompute the signature and compare. An attacker
            # who somehow modified the entries dict would still need the
            # secret to forge a matching signature.
            expected = _sign(self._secret, nonce, path, expiry)
            if not hmac.compare_digest(expected, _sig):
                return None
            return path

    # ── internal ─────────────────────────────────────────────────────

    def _sweep_expired_locked(self) -> None:
        """Opportunistic cleanup of expired entries. Caller holds the lock."""
        now = time.monotonic()
        expired = [tok for tok, (_, exp) in self._entries.items() if exp <= now]
        for tok in expired:
            self._entries.pop(tok, None)
