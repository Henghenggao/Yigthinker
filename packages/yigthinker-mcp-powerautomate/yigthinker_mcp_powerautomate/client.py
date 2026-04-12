"""httpx.AsyncClient wrapper around Power Automate Flow Management API endpoints.

- Raw ``httpx.AsyncClient``, no PA SDK, no ``azure-mgmt-web`` (D-15).
- Constructor takes exactly 2 args: ``auth`` and ``base_url`` (D-16).
- 3 attempts with exponential backoff ``(1s, 2s, 4s)`` on 5xx and
  ``httpx.NetworkError``; 4xx fails immediately (D-16).
- 30s timeout per request.

All endpoints target the Flow Management API at ``https://api.flow.microsoft.com``
using ``api-version=2016-11-01`` (D-18).
"""
from __future__ import annotations

import httpx

from .auth import PowerAutomateAuth

RETRY_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0)
REQUEST_TIMEOUT_S: float = 30.0
API_VERSION: str = "2016-11-01"


class PowerAutomateClient:
    """Thin async wrapper around Power Automate Flow Management API endpoints.

    One client instance per ``call_tool`` invocation is the expected lifecycle;
    the thundering-herd fix lives inside ``PowerAutomateAuth`` via
    ``asyncio.Lock``, so sharing the auth object across clients is safe.
    """

    def __init__(self, auth: PowerAutomateAuth, base_url: str) -> None:
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)

    async def aclose(self) -> None:
        raise NotImplementedError("Plan 12-03 replaces this")

    async def __aenter__(self) -> "PowerAutomateClient":
        raise NotImplementedError("Plan 12-03 replaces this")

    async def __aexit__(self, *exc_info: object) -> None:
        raise NotImplementedError("Plan 12-03 replaces this")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        raise NotImplementedError("Plan 12-03 replaces this")
