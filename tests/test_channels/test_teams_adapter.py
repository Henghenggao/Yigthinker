"""Tests for Teams adapter session key derivation, immediate ACK, Graph API response,
retry logic, MSAL failure handling, and serviceUrl configuration."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as hmac_mod
import json
import sys
from types import ModuleType

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.channels.teams.adapter import TeamsAdapter


def _mock_msal_module() -> ModuleType:
    """Create a mock msal module for tests (msal is not installed in test env)."""
    mock_mod = ModuleType("msal")
    mock_mod.ConfidentialClientApplication = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    return mock_mod


@pytest.fixture
def adapter():
    """TeamsAdapter with test config."""
    return TeamsAdapter({
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "webhook_secret": base64.b64encode(b"test-key").decode(),
        "session_scope": "per-sender",
    })


# --- TEAMS-03: Session key from AAD object ID ---


def test_session_key_per_sender(adapter):
    """Per-sender scope derives key from aadObjectId."""
    event = {"from": {"aadObjectId": "user-abc-123"}}
    key = adapter.session_key(event)
    assert key == "teams:user-abc-123"


def test_session_key_missing_aad_id(adapter):
    """Missing aadObjectId falls back to 'unknown'."""
    event = {"from": {}}
    key = adapter.session_key(event)
    assert key == "teams:unknown"


def test_session_key_per_channel():
    """Per-channel scope derives key from channel ID."""
    adapter = TeamsAdapter({
        "tenant_id": "t",
        "client_id": "c",
        "client_secret": "s",
        "session_scope": "per-channel",
    })
    event = {
        "from": {"aadObjectId": "user-1"},
        "channelData": {"channel": {"id": "channel-xyz"}},
    }
    key = adapter.session_key(event)
    assert key == "teams:chat:channel-xyz"


def test_session_key_per_channel_fallback_to_sender():
    """Per-channel scope falls back to per-sender when channel ID missing."""
    adapter = TeamsAdapter({
        "tenant_id": "t",
        "client_id": "c",
        "client_secret": "s",
        "session_scope": "per-channel",
    })
    event = {"from": {"aadObjectId": "user-1"}, "channelData": {}}
    key = adapter.session_key(event)
    assert key == "teams:user-1"


# --- D-05: Webhook returns 200 immediately with thinking card ---


@pytest.mark.asyncio
async def test_webhook_returns_thinking_card_immediately(adapter):
    """Webhook returns 200 with render_thinking() card immediately per D-05, does not block on handle_message."""
    mock_gateway = MagicMock()
    mock_gateway.app = MagicMock()
    # handle_message should NOT be awaited in the webhook handler itself
    mock_gateway.handle_message = AsyncMock(return_value="Analysis complete")

    route_handler = None

    def capture_post(path):
        def decorator(fn):
            nonlocal route_handler
            route_handler = fn
            return fn
        return decorator

    mock_gateway.app.post = capture_post

    # Inject mock msal module so import msal succeeds inside start()
    mock_msal = _mock_msal_module()
    with patch.dict(sys.modules, {"msal": mock_msal}):
        await adapter.start(mock_gateway)

    assert route_handler is not None

    # Build a mock request with valid HMAC
    secret_b64 = adapter._webhook_secret
    body_dict = {
        "text": "analyze sales",
        "from": {"aadObjectId": "user-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-123"},
    }
    body_bytes = json.dumps(body_dict).encode()
    key_bytes = base64.b64decode(secret_b64)
    sig = base64.b64encode(
        hmac_mod.new(key_bytes, body_bytes, hashlib.sha256).digest()
    ).decode()

    mock_request = AsyncMock()
    mock_request.body = AsyncMock(return_value=body_bytes)
    mock_request.headers = {"Authorization": f"HMAC {sig}"}

    # Patch asyncio.create_task to capture the coroutine without running it
    created_tasks = []

    def mock_create_task(coro):
        created_tasks.append(coro)
        # Cancel the coroutine to avoid "was never awaited" warning
        coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=mock_create_task):
        response = await route_handler(mock_request)

    # Verify response is immediate 200 with thinking card
    response_body = json.loads(response.body.decode())
    assert response_body["type"] == "message"
    assert len(response_body["attachments"]) == 1
    card = response_body["attachments"][0]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    # render_thinking() returns "Analyzing..." card
    assert card["content"]["type"] == "AdaptiveCard"
    text_block = card["content"]["body"][0]
    assert "Analyzing" in text_block["text"]

    # Verify handle_message was NOT called synchronously in the webhook handler
    # (it runs in the background task created by asyncio.create_task)
    mock_gateway.handle_message.assert_not_called()

    # Verify a background task WAS created
    assert len(created_tasks) == 1


# --- TEAMS-02: send_response via Graph API ---


@pytest.mark.asyncio
async def test_send_response_posts_adaptive_card_via_graph_api(adapter):
    """send_response() POSTs an Adaptive Card to Bot Framework API (TEAMS-02)."""
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "test-token-123",
    }
    adapter._gateway = MagicMock()

    event = {
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-456"},
    }

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await adapter.send_response(event, "Analysis complete")

        # Verify the POST was made to the correct Bot Framework URL
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "v3/conversations/conv-456/activities" in url

        # Verify the payload contains an Adaptive Card
        payload = call_args[1]["json"]
        assert payload["type"] == "message"
        assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
        card = payload["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["body"][0]["text"] == "Analysis complete"

        # Verify auth header uses MSAL token
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-token-123"


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_hmac(adapter):
    """Webhook returns 401 for invalid HMAC signature."""
    mock_gateway = MagicMock()
    mock_gateway.app = MagicMock()

    route_handler = None

    def capture_post(path):
        def decorator(fn):
            nonlocal route_handler
            route_handler = fn
            return fn
        return decorator

    mock_gateway.app.post = capture_post

    # Inject mock msal module so import msal succeeds inside start()
    mock_msal = _mock_msal_module()
    with patch.dict(sys.modules, {"msal": mock_msal}):
        await adapter.start(mock_gateway)

    body_bytes = b'{"text": "hello"}'
    mock_request = AsyncMock()
    mock_request.body = AsyncMock(return_value=body_bytes)
    mock_request.headers = {"Authorization": "HMAC invalid-signature"}

    response = await route_handler(mock_request)
    assert response.status_code == 401


# --- Retry logic for Graph API failures ---


@pytest.mark.asyncio
async def test_send_response_retries_on_server_error():
    """send_response retries on 500/502/503/504 with exponential backoff."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "max_retries": 3, "timeout": 5.0,
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "tok",
    }

    event = {
        "serviceUrl": "https://smba.example.com/",
        "conversation": {"id": "conv-1"},
    }

    # First two calls return 503, third returns 200
    mock_resp_503 = MagicMock()
    mock_resp_503.status_code = 503
    mock_resp_503.text = "Service Unavailable"
    mock_resp_503.request = MagicMock()

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return mock_resp_503
        return mock_resp_200

    with patch("httpx.AsyncClient") as mock_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

    assert call_count == 3
    # Verify backoff delays: 1s, 2s
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@pytest.mark.asyncio
async def test_send_response_no_retry_on_client_error():
    """send_response does NOT retry on 400/401/403 — non-retryable."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "max_retries": 3,
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "tok",
    }

    event = {
        "serviceUrl": "https://smba.example.com/",
        "conversation": {"id": "conv-1"},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

        # Only called once — no retry for 403
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_response_retries_on_timeout():
    """send_response retries on httpx.TimeoutException."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "max_retries": 2, "timeout": 5.0,
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "tok",
    }

    event = {
        "serviceUrl": "https://smba.example.com/",
        "conversation": {"id": "conv-1"},
    }

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("timed out")

    with patch("httpx.AsyncClient") as mock_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

    assert call_count == 2


# --- MSAL token failure ---


@pytest.mark.asyncio
async def test_send_response_aborts_on_msal_failure():
    """send_response returns early when MSAL token acquisition fails."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "error": "invalid_client",
        "error_description": "Client secret is expired",
    }

    event = {
        "serviceUrl": "https://smba.example.com/",
        "conversation": {"id": "conv-1"},
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

        # httpx should never be called if token fails
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_token_returns_none_when_msal_not_initialized():
    """_acquire_token returns None with descriptive log when MSAL app is None."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
    })
    adapter._msal_app = None

    token = adapter._acquire_token()
    assert token is None


# --- serviceUrl configuration for private deployments ---


@pytest.mark.asyncio
async def test_service_url_override_for_private_deployment():
    """Configured service_url takes precedence over event serviceUrl."""
    private_url = "https://teams.internal.corp.com/botframework/"
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "service_url": private_url,
        "max_retries": 1,
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "tok",
    }

    event = {
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-1"},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        # Must use private URL, not the event's public serviceUrl
        assert url.startswith(private_url.rstrip("/"))
        assert "smba.trafficmanager.net" not in url


@pytest.mark.asyncio
async def test_service_url_falls_back_to_event():
    """When service_url not configured, uses event serviceUrl."""
    adapter = TeamsAdapter({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "max_retries": 1,
    })
    adapter._msal_app = MagicMock()
    adapter._msal_app.acquire_token_for_client.return_value = {
        "access_token": "tok",
    }

    event_url = "https://smba.trafficmanager.net/emea/"
    event = {
        "serviceUrl": event_url,
        "conversation": {"id": "conv-1"},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        await adapter.send_response(event, "Hello")

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert url.startswith(event_url.rstrip("/"))


# --- Settings integration ---


def test_default_settings_include_webhook_secret():
    """DEFAULT_SETTINGS includes webhook_secret, service_url, max_retries, timeout."""
    from yigthinker.settings import DEFAULT_SETTINGS
    teams = DEFAULT_SETTINGS["channels"]["teams"]
    assert "webhook_secret" in teams
    assert "service_url" in teams
    assert "max_retries" in teams
    assert "timeout" in teams
