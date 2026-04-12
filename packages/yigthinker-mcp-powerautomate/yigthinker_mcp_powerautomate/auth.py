"""MSAL ConfidentialClientApplication auth for Power Automate Flow Management API.

Cloud-only: uses ``msal.ConfidentialClientApplication.acquire_token_for_client``
to obtain an access token scoped to ``https://service.flow.microsoft.com//.default``.
Caches the access token with a 60-second safety margin and serializes refresh via
``asyncio.Lock`` to avoid thundering-herd token requests (Phase 11 Pitfall 4).

The double-slash in the scope string is a documented Microsoft API quirk, NOT a typo.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

DEFAULT_SCOPE = "https://service.flow.microsoft.com//.default"
SAFETY_MARGIN_S = 60


@dataclass
class PowerAutomateAuth:
    """MSAL client credentials wrapper for Power Automate.

    Per CONTEXT.md D-09 — ``asyncio.Lock`` is created via ``field(default_factory=...)``,
    NEVER ``default=asyncio.Lock()``, to avoid sharing a single lock across instances.
    """

    tenant_id: str
    client_id: str
    client_secret: str
    scope: str = DEFAULT_SCOPE
    authority: str | None = None
    _token: str | None = field(default=None, repr=False)
    _expires_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get_token(self) -> str:
        """Return a valid access token, refreshing via MSAL if expired.

        Concurrency-safe via ``asyncio.Lock`` — multiple parallel callers
        see at most one ``acquire_token_for_client`` call per refresh.
        """
        raise NotImplementedError("Plan 12-02 replaces this")

    async def auth_headers(self) -> dict[str, str]:
        """Return Authorization header dict for downstream Flow Management API calls."""
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
