"""Unit tests for yigthinker_mcp_uipath.auth.UipathAuth (CONTEXT.md D-23)."""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import TOKEN_URL, UipathAuth

pytestmark = pytest.mark.asyncio


def _make_auth(scope: str = "OR.Execution OR.Jobs") -> UipathAuth:
    return UipathAuth(
        client_id="id",
        client_secret="secret",
        tenant_name="DefaultTenant",
        organization="acmecorp",
        scope=scope,
    )


@respx.mock
async def test_token_acquisition_and_caching():
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok-1", "expires_in": 3600}
        )
    )
    auth = _make_auth()
    async with httpx.AsyncClient() as http:
        t1 = await auth.get_token(http)
        t2 = await auth.get_token(http)
    assert t1 == "tok-1"
    assert t2 == "tok-1"
    assert token_route.call_count == 1


@respx.mock
async def test_form_body_uses_space_separated_scope():
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok", "expires_in": 3600}
        )
    )
    auth = _make_auth(scope="OR.Execution OR.Jobs OR.Folders.Read")
    async with httpx.AsyncClient() as http:
        await auth.get_token(http)
    body = token_route.calls.last.request.content.decode()
    assert "grant_type=client_credentials" in body
    # x-www-form-urlencoded encodes spaces as + signs.
    assert "scope=OR.Execution+OR.Jobs+OR.Folders.Read" in body
    assert "client_id=id" in body
    assert "client_secret=secret" in body
    # Pitfall 3: NEVER comma-separated
    assert "scope=OR.Execution%2C" not in body
    assert "scope=OR.Execution," not in body


@respx.mock
async def test_token_refresh_on_expiry(monkeypatch):
    token_route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "tok-1", "expires_in": 1}),
            httpx.Response(200, json={"access_token": "tok-2", "expires_in": 3600}),
        ]
    )
    auth = _make_auth()
    fake_now = [100.0]
    # Patch the time.monotonic reference imported into auth.py at module load.
    monkeypatch.setattr(
        "yigthinker_mcp_uipath.auth.time.monotonic",
        lambda: fake_now[0],
    )
    async with httpx.AsyncClient() as http:
        t1 = await auth.get_token(http)
        # Advance past expires_in (1s) + safety margin (60s)
        fake_now[0] += 120.0
        t2 = await auth.get_token(http)
    assert t1 == "tok-1"
    assert t2 == "tok-2"
    assert token_route.call_count == 2


@respx.mock
async def test_401_on_invalid_credentials():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    auth = UipathAuth(
        client_id="bad",
        client_secret="bad",
        tenant_name="DefaultTenant",
        organization="acmecorp",
        scope="OR.Execution",
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(httpx.HTTPStatusError):
            await auth.get_token(http)


@respx.mock
async def test_auth_headers_returns_bearer():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok-1", "expires_in": 3600}
        )
    )
    auth = _make_auth()
    async with httpx.AsyncClient() as http:
        headers = await auth.auth_headers(http)
    assert headers == {"Authorization": "Bearer tok-1"}


@respx.mock
async def test_concurrent_get_token_one_request():
    """Pitfall 4: asyncio.Lock guards thundering-herd token acquisition."""
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok-concurrent", "expires_in": 3600}
        )
    )
    auth = _make_auth()
    async with httpx.AsyncClient() as http:
        results = await asyncio.gather(
            auth.get_token(http),
            auth.get_token(http),
            auth.get_token(http),
        )
    assert all(t == "tok-concurrent" for t in results)
    assert token_route.call_count == 1
