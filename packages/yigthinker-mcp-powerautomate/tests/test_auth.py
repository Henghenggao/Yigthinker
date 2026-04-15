"""Unit tests for yigthinker_mcp_powerautomate.auth.PowerAutomateAuth (D-26/D-27).

MSAL is mocked via monkeypatch on the _app cached_property -- NOT via respx,
because MSAL uses its own internal HTTP stack (``requests``, not ``httpx``).

Test matrix (D-27 Row 1):
  - token acquisition (scopes as list[str])
  - token caching (no second MSAL call within expiry)
  - expired-token refresh
  - MSAL error raises RuntimeError
  - asyncio.Lock concurrent-get thundering-herd guard
  - custom scope forwarded to MSAL
  - default authority derived from tenant_id
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from yigthinker_mcp_powerautomate.auth import (
    DEFAULT_SCOPE,
    PowerAutomateAuth,
)

pytestmark = pytest.mark.asyncio


def _make_auth(
    scope: str = DEFAULT_SCOPE,
    tenant_id: str = "test-tenant",
    authority: str | None = None,
) -> PowerAutomateAuth:
    return PowerAutomateAuth(
        tenant_id=tenant_id,
        client_id="test-client-id",
        client_secret="test-client-secret",
        scope=scope,
        authority=authority,
    )


def _mock_msal_app(
    auth: PowerAutomateAuth,
    token_response: dict | None = None,
) -> MagicMock:
    """Inject a MagicMock as the MSAL ConfidentialClientApplication on auth._app.

    Uses instance __dict__ injection so ``cached_property`` finds the mock
    without replacing the class-level descriptor (which would leak between tests).
    """
    if token_response is None:
        token_response = {
            "access_token": "tok-1",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    mock_app = MagicMock()
    mock_app.acquire_token_for_client.return_value = token_response
    # cached_property stores its result in instance.__dict__["_app"].
    # Writing directly to the instance dict pre-populates that cache.
    auth.__dict__["_app"] = mock_app
    return mock_app


async def test_token_acquisition():
    """acquire_token_for_client called with scopes as list[str], returns token."""
    auth = _make_auth()
    mock_app = _mock_msal_app(auth)

    token = await auth.get_token()

    assert token == "tok-1"
    mock_app.acquire_token_for_client.assert_called_once_with(
        scopes=[DEFAULT_SCOPE],
    )


async def test_token_caching_no_second_msal_call():
    """Second get_token() within expiry window reuses cached token."""
    auth = _make_auth()
    mock_app = _mock_msal_app(auth)

    t1 = await auth.get_token()
    t2 = await auth.get_token()

    assert t1 == "tok-1"
    assert t2 == "tok-1"
    assert mock_app.acquire_token_for_client.call_count == 1


async def test_expired_token_triggers_refresh(monkeypatch):
    """Token refresh fires when monotonic clock passes expiry - safety margin."""
    auth = _make_auth()
    fake_now = [100.0]
    monkeypatch.setattr(
        "yigthinker_mcp_powerautomate.auth.time.monotonic",
        lambda: fake_now[0],
    )

    mock_app = MagicMock()
    mock_app.acquire_token_for_client.side_effect = [
        {"access_token": "tok-1", "expires_in": 1, "token_type": "Bearer"},
        {"access_token": "tok-2", "expires_in": 3600, "token_type": "Bearer"},
    ]
    auth.__dict__["_app"] = mock_app

    t1 = await auth.get_token()
    # Advance past expires_in (1s) + safety margin (60s)
    fake_now[0] += 120.0
    t2 = await auth.get_token()

    assert t1 == "tok-1"
    assert t2 == "tok-2"
    assert mock_app.acquire_token_for_client.call_count == 2


async def test_msal_error_raises_runtime_error():
    """MSAL error response (no access_token key) raises RuntimeError."""
    auth = _make_auth()
    _mock_msal_app(
        auth,
        token_response={
            "error": "AADSTS65001",
            "error_description": "The user or administrator has not consented",
        },
    )

    with pytest.raises(RuntimeError, match="AADSTS65001"):
        await auth.get_token()


async def test_concurrent_get_token_one_request():
    """asyncio.Lock guards thundering-herd token acquisition (Pitfall 4)."""
    auth = _make_auth()
    mock_app = _mock_msal_app(auth)

    results = await asyncio.gather(
        auth.get_token(),
        auth.get_token(),
        auth.get_token(),
        auth.get_token(),
        auth.get_token(),
    )

    assert all(t == "tok-1" for t in results)
    assert mock_app.acquire_token_for_client.call_count == 1


async def test_custom_scope_passed_to_msal():
    """Custom scope string forwarded as list[str] to acquire_token_for_client."""
    custom_scope = "https://custom.scope//.default"
    auth = _make_auth(scope=custom_scope)
    mock_app = _mock_msal_app(auth)

    await auth.get_token()

    mock_app.acquire_token_for_client.assert_called_once_with(
        scopes=[custom_scope],
    )


async def test_default_authority_uses_tenant_id(monkeypatch):
    """When authority is None, MSAL app uses https://login.microsoftonline.com/{tenant_id}."""
    mock_cca_instance = MagicMock()
    mock_cca_class = MagicMock(return_value=mock_cca_instance)

    monkeypatch.setattr(
        "yigthinker_mcp_powerautomate.auth.msal.ConfidentialClientApplication",
        mock_cca_class,
    )

    auth = _make_auth(tenant_id="my-tenant", authority=None)
    # Access _app to trigger ConfidentialClientApplication creation.
    # Do NOT pre-populate __dict__["_app"] -- let cached_property run the real code.
    _ = auth._app

    mock_cca_class.assert_called_once_with(
        client_id="test-client-id",
        client_credential="test-client-secret",
        authority="https://login.microsoftonline.com/my-tenant",
    )
