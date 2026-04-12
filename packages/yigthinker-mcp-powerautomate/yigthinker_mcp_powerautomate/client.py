"""httpx.AsyncClient wrapper around Power Automate Flow Management API endpoints.

Implemented in Plan 12-03 per CONTEXT.md D-15..D-18.

- **D-15:** Raw ``httpx.AsyncClient``, no PA SDK, no ``azure-mgmt-web``. Zero extra runtime deps.
- **D-16 (LOCKED constructor):** ``PowerAutomateClient(auth, base_url)`` -- exactly
  2 args. The ``httpx.AsyncClient`` is created INTERNALLY in ``__init__``.
  Callers NEVER pass an ``http`` kwarg. Plan 12-05 tool handlers match this.
- **D-16 retry:** 3 attempts with exponential backoff ``(1s, 2s, 4s)`` on 5xx
  and ``httpx.NetworkError``. 4xx fails immediately via ``raise_for_status()``.
  30s timeout per request.
- **D-17:** HTTP errors propagate to the tool handler layer (Plan 12-05), which
  converts them to ``ToolResult(is_error=True, content=...)``. This module does
  NOT swallow exceptions.
- **D-18:** All endpoints use ``environment_id`` in URL path + ``api-version=2016-11-01``
  query param.

All endpoints target the Flow Management API at ``https://api.flow.microsoft.com``
using ``api-version=2016-11-01``.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .auth import PowerAutomateAuth

RETRY_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0)
REQUEST_TIMEOUT_S: float = 30.0
API_VERSION: str = "2016-11-01"

_PROVIDER_PATH = "/providers/Microsoft.ProcessSimple"


class PowerAutomateClient:
    """Thin async wrapper around Power Automate Flow Management API endpoints.

    One client instance per ``call_tool`` invocation is the expected lifecycle;
    the thundering-herd fix lives inside ``PowerAutomateAuth`` via
    ``asyncio.Lock``, so sharing the auth object across clients is safe.
    """

    def __init__(self, auth: PowerAutomateAuth, base_url: str) -> None:
        # D-16 LOCKED: exactly 2 args. httpx.AsyncClient is internal.
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "PowerAutomateClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal request helper with retry/backoff
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Perform a request with auth headers, api-version param, and retry.

        Retry semantics per D-16:
        - 3 attempts total (``RETRY_BACKOFFS`` is a 3-tuple).
        - Retry on 5xx responses and ``httpx.NetworkError``.
        - 4xx responses raise immediately via ``resp.raise_for_status()``.
        - Sleep ``RETRY_BACKOFFS[attempt]`` between attempts; the final
          attempt raises instead of sleeping.
        """
        url = f"{self.base_url}{path}"

        # D-18: api-version appended to every request.
        if params is None:
            params = {}
        params["api-version"] = API_VERSION

        last_exc: Exception | None = None
        for attempt, backoff in enumerate(RETRY_BACKOFFS):
            is_last_attempt = attempt == len(RETRY_BACKOFFS) - 1
            try:
                token = await self.auth.get_token()
                headers = {"Authorization": f"Bearer {token}"}
                resp = await self._http.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
            except httpx.NetworkError as exc:
                last_exc = exc
                if is_last_attempt:
                    raise
                await asyncio.sleep(backoff)
                continue

            if 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if is_last_attempt:
                    resp.raise_for_status()
                await asyncio.sleep(backoff)
                continue

            if 400 <= resp.status_code < 500:
                # D-16: 4xx fails immediately, no retry.
                resp.raise_for_status()

            return resp

        # Unreachable in practice -- the loop either returns or raises above.
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Domain methods (thin wrappers around _request)
    # ------------------------------------------------------------------

    async def create_flow(
        self,
        env_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /providers/Microsoft.ProcessSimple/environments/{env_id}/flows"""
        resp = await self._request(
            "POST",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows",
            json_body=body,
        )
        return dict(resp.json())

    async def get_flow(
        self,
        env_id: str,
        flow_id: str,
    ) -> dict[str, Any]:
        """GET .../environments/{env_id}/flows/{flow_id}"""
        resp = await self._request(
            "GET",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows/{flow_id}",
        )
        return dict(resp.json())

    async def trigger_flow_run(
        self,
        env_id: str,
        flow_id: str,
        trigger_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST .../flows/{flow_id}/triggers/manual/run"""
        resp = await self._request(
            "POST",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows/{flow_id}/triggers/manual/run",
            json_body=trigger_input or {},
        )
        return dict(resp.json())

    async def list_flow_runs(
        self,
        env_id: str,
        flow_id: str,
        top: int = 10,
    ) -> list[dict[str, Any]]:
        """GET .../flows/{flow_id}/runs with $top param."""
        resp = await self._request(
            "GET",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows/{flow_id}/runs",
            params={"$top": top},
        )
        data = resp.json()
        return list(data.get("value", []))

    async def stop_flow(
        self,
        env_id: str,
        flow_id: str,
    ) -> dict[str, Any]:
        """POST .../flows/{flow_id}/stop (disable)."""
        resp = await self._request(
            "POST",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows/{flow_id}/stop",
        )
        return dict(resp.json())

    async def start_flow(
        self,
        env_id: str,
        flow_id: str,
    ) -> dict[str, Any]:
        """POST .../flows/{flow_id}/start (enable)."""
        resp = await self._request(
            "POST",
            f"{_PROVIDER_PATH}/environments/{env_id}/flows/{flow_id}/start",
        )
        return dict(resp.json())

    async def list_connections(
        self,
        env_id: str,
        connector_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET .../connections, optionally filtered by connector name."""
        params: dict[str, Any] = {}
        if connector_name is not None:
            params["$filter"] = f"apiId eq '*{connector_name}*'"
        resp = await self._request(
            "GET",
            f"{_PROVIDER_PATH}/environments/{env_id}/connections",
            params=params,
        )
        data = resp.json()
        return list(data.get("value", []))
