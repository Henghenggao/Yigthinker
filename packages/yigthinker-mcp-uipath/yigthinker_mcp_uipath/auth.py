"""OAuth2 client credentials auth for UiPath Automation Cloud (CONTEXT.md D-08..D-11).

Cloud-only: posts to ``https://cloud.uipath.com/identity_/connect/token`` with
``grant_type=client_credentials``. Caches the access token with a 60-second
safety margin and serializes refresh via ``asyncio.Lock`` to avoid thundering-
herd token requests (Pitfall 4).

On-prem Standalone Orchestrator API key path is OUT OF SCOPE for Phase 11
per CONTEXT.md "Deferred Ideas".
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token"
SAFETY_MARGIN_S = 60


@dataclass
class UipathAuth:
    """OAuth2 client credentials wrapper.

    Per CONTEXT.md D-09 — exact constructor signature is locked. The 5 tool
    handlers in Plan 11-05 inject ``Authorization: Bearer <token>`` via
    ``auth_headers(http)``. The ``X-UIPATH-OrganizationUnitId`` header is the
    responsibility of OrchestratorClient (Plan 11-03), not this class.
    """

    client_id: str
    client_secret: str
    tenant_name: str
    organization: str
    scope: str  # space-separated per OAuth2 RFC 6749 (Pitfall 3)
    _token: str | None = field(default=None, repr=False)
    _expires_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get_token(self, http: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if expired.

        Concurrency-safe via ``asyncio.Lock`` — multiple parallel callers
        see at most one POST to the token endpoint per refresh.
        """
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._expires_at - SAFETY_MARGIN_S:
                return self._token
            resp = await http.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            self._token = payload["access_token"]
            self._expires_at = now + float(payload.get("expires_in", 3600))
            return self._token

    async def auth_headers(self, http: httpx.AsyncClient) -> dict[str, str]:
        """Return Authorization header dict for downstream Orchestrator calls."""
        token = await self.get_token(http)
        return {"Authorization": f"Bearer {token}"}
