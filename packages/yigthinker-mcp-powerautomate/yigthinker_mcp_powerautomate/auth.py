"""MSAL ConfidentialClientApplication auth for Power Automate Flow Management API.

Cloud-only: uses ``msal.ConfidentialClientApplication.acquire_token_for_client``
to obtain an access token scoped to ``https://service.flow.microsoft.com//.default``.
Caches the access token with a 60-second safety margin and serializes refresh via
``asyncio.Lock`` to avoid thundering-herd token requests (Phase 11 Pitfall 4).

The double-slash in the scope string is a documented Microsoft API quirk, NOT a typo.

Unlike Phase 11 (raw httpx OAuth2 against UiPath), this module delegates HTTP
entirely to MSAL -- ``get_token()`` takes NO ``http`` parameter (D-08).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from functools import cached_property

import msal

DEFAULT_SCOPE = "https://service.flow.microsoft.com//.default"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/{tenant_id}"
SAFETY_MARGIN_S = 60


@dataclass
class PowerAutomateAuth:
    """MSAL client credentials wrapper for Power Automate.

    Per CONTEXT.md D-09 -- ``asyncio.Lock`` is created via ``field(default_factory=...)``,
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

    @cached_property
    def _app(self) -> msal.ConfidentialClientApplication:
        """Create the MSAL ConfidentialClientApplication lazily."""
        authority = self.authority or DEFAULT_AUTHORITY.format(
            tenant_id=self.tenant_id,
        )
        return msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority,
        )

    async def get_token(self) -> str:
        """Return a valid access token, refreshing via MSAL if expired.

        Concurrency-safe via ``asyncio.Lock`` -- multiple parallel callers
        see at most one ``acquire_token_for_client`` call per refresh.

        Raises ``RuntimeError`` if MSAL returns an error response (e.g.
        AADSTS65001 admin consent not granted).
        """
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._expires_at - SAFETY_MARGIN_S:
                return self._token
            result = self._app.acquire_token_for_client(
                scopes=[self.scope],
            )
            if "access_token" in result:
                self._token = result["access_token"]
                self._expires_at = now + float(result.get("expires_in", 3600))
                return self._token
            # MSAL error response -- surface the error code and description.
            error = result.get("error", "unknown_error")
            desc = result.get("error_description", "no description")
            raise RuntimeError(f"MSAL token error: {error} -- {desc}")

    async def auth_headers(self) -> dict[str, str]:
        """Return Authorization header dict for downstream Flow Management API calls."""
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
