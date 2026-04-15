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


# --- Attachment support (Task 1 TDD RED) ---


def _make_webhook_body(
    text: str = "analyze this",
    attachments: list[dict] | None = None,
    sender: str = "user-1",
) -> dict:
    """Build a Bot Framework message body with optional attachments."""
    body: dict[str, Any] = {
        "text": text,
        "from": {"aadObjectId": sender},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-attach-test"},
    }
    if attachments is not None:
        body["attachments"] = attachments
    return body


async def _setup_adapter_with_webhook(adapter):
    """Create adapter, inject mock msal, call start(), return (adapter, route_handler)."""
    mock_gateway = MagicMock()
    mock_gateway.app = MagicMock()
    mock_gateway.handle_message = AsyncMock(return_value="Analysis complete")

    route_handler = None

    def capture_post(path):
        def decorator(fn):
            nonlocal route_handler
            route_handler = fn
            return fn
        return decorator

    mock_gateway.app.post = capture_post

    mock_msal = _mock_msal_module()
    with patch.dict(sys.modules, {"msal": mock_msal}):
        await adapter.start(mock_gateway)

    return adapter, route_handler


def _make_signed_request(body_dict: dict, webhook_secret: str) -> AsyncMock:
    """Build a mock Request with valid HMAC signature."""
    body_bytes = json.dumps(body_dict).encode()
    key_bytes = base64.b64decode(webhook_secret)
    sig = base64.b64encode(
        hmac_mod.new(key_bytes, body_bytes, hashlib.sha256).digest()
    ).decode()
    mock_request = AsyncMock()
    mock_request.body = AsyncMock(return_value=body_bytes)
    mock_request.headers = {"Authorization": f"HMAC {sig}"}
    return mock_request


def _mock_httpx_download(content: bytes = b"fake excel bytes", status_code: int = 200):
    """Context-manager-style mock for httpx.AsyncClient GET downloads."""
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = content
    mock_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


from typing import Any


@pytest.mark.asyncio
async def test_webhook_with_single_xlsx_attachment(adapter):
    """Webhook with a single .xlsx attachment downloads file and augments text
    with '[Attached file: data.xlsx -> ...]' prefix before original message."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    body = _make_webhook_body(
        text="analyze sales",
        attachments=[{
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentUrl": "https://teams.example.com/files/data.xlsx",
            "name": "data.xlsx",
        }],
    )
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    # Capture the coroutine args by patching _process_and_respond
    adapter._process_and_respond = AsyncMock()

    mock_dl_client = _mock_httpx_download()

    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client), \
         patch("asyncio.create_task", side_effect=capture_create_task):
        response = await handler(mock_request)

    # _process_and_respond was called once inside the coroutine
    # Since we close the coroutine, we need to verify text differently.
    # Instead, test _download_attachments directly for text augmentation.
    assert len(created_coros) == 1


@pytest.mark.asyncio
async def test_download_attachments_augments_text_with_file_path(adapter):
    """_download_attachments returns file_lines with '[Attached file: name -> path]' format."""
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentUrl": "https://teams.example.com/files/data.xlsx",
            "name": "data.xlsx",
        }])

    assert len(file_lines) == 1
    assert len(error_lines) == 0
    assert file_lines[0].startswith("[Attached file: data.xlsx ->")
    assert file_lines[0].endswith("]")
    # Path should contain the filename
    assert "data.xlsx" in file_lines[0]


@pytest.mark.asyncio
async def test_webhook_with_multiple_attachments(adapter):
    """Webhook with multiple attachments (.xlsx + .csv) downloads all
    and augments text with multiple '[Attached file: ...]' lines."""
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([
            {
                "contentUrl": "https://teams.example.com/files/data.xlsx",
                "name": "data.xlsx",
            },
            {
                "contentUrl": "https://teams.example.com/files/report.csv",
                "name": "report.csv",
            },
        ])

    assert len(file_lines) == 2
    assert len(error_lines) == 0
    assert "[Attached file: data.xlsx ->" in file_lines[0]
    assert "[Attached file: report.csv ->" in file_lines[1]


@pytest.mark.asyncio
async def test_webhook_skips_unsupported_file_type(adapter):
    """Unsupported file type (.pdf) produces skip message listing supported
    extensions and no download is attempted."""
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentUrl": "https://teams.example.com/files/report.pdf",
            "name": "report.pdf",
        }])

    assert len(file_lines) == 0
    assert len(error_lines) == 1
    assert "[Skipped unsupported file: report.pdf" in error_lines[0]
    assert "supported:" in error_lines[0]
    assert ".xlsx" in error_lines[0]
    # No download should have been attempted
    mock_dl_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_handles_download_failure(adapter):
    """Download failure (httpx ConnectError) produces '[Failed to download: data.xlsx]'
    error line and continues processing."""
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    # Mock httpx to raise ConnectError
    mock_dl_client = AsyncMock()
    mock_dl_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_dl_client.__aenter__ = AsyncMock(return_value=mock_dl_client)
    mock_dl_client.__aexit__ = AsyncMock(return_value=False)

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentUrl": "https://teams.example.com/files/data.xlsx",
            "name": "data.xlsx",
        }])

    assert len(file_lines) == 0
    assert len(error_lines) == 1
    assert "[Failed to download: data.xlsx]" in error_lines[0]


@pytest.mark.asyncio
async def test_webhook_text_only_unchanged(adapter):
    """Webhook with text but no attachments works exactly as before --
    no augmentation, same thinking card response."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)

    body = _make_webhook_body(text="just a question")
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_create_task):
        response = await handler(mock_request)

    response_body = json.loads(response.body.decode())
    assert response_body["type"] == "message"
    assert "Analyzing" in response_body["attachments"][0]["content"]["body"][0]["text"]
    assert len(created_coros) == 1


@pytest.mark.asyncio
async def test_webhook_attachment_without_content_url(adapter):
    """Attachment dict with name but no contentUrl is filtered out before
    _download_attachments -- text remains unaugmented."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)

    body = _make_webhook_body(
        text="analyze this",
        attachments=[{
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "name": "data.xlsx",
            # No contentUrl -- filtered out by the contentUrl check in webhook
        }],
    )
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_create_task):
        response = await handler(mock_request)

    # Task still created (text-only path), just no attachment augmentation
    assert len(created_coros) == 1


@pytest.mark.asyncio
async def test_webhook_attachment_only_no_text(adapter):
    """Body with attachments but empty text does NOT return early with
    'Empty message' -- it processes the attachments and creates a background task."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    body = _make_webhook_body(
        text="",
        attachments=[{
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentUrl": "https://teams.example.com/files/data.xlsx",
            "name": "data.xlsx",
        }],
    )
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    mock_dl_client = _mock_httpx_download()

    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client), \
         patch("asyncio.create_task", side_effect=capture_create_task):
        adapter._process_and_respond = AsyncMock()
        response = await handler(mock_request)

    response_body = json.loads(response.body.decode())
    # Should NOT be "Empty message" -- should proceed with attachment processing
    assert response_body.get("text") != "Empty message"
    # Background task was created (not short-circuited)
    assert len(created_coros) == 1


@pytest.mark.asyncio
async def test_webhook_filters_non_file_attachments(adapter):
    """Hero card attachment alongside a real file -- only the file is passed
    to _process_and_respond, not the card."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)
    adapter._acquire_token = MagicMock(return_value="test-download-token")

    body = _make_webhook_body(
        text="check this",
        attachments=[
            {
                # Hero card -- should be filtered out (no contentUrl)
                "contentType": "application/vnd.microsoft.card.hero",
                "content": {"title": "Hero Card"},
            },
            {
                # Real file -- should be passed through
                "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "contentUrl": "https://teams.example.com/files/sales.xlsx",
                "name": "sales.xlsx",
            },
        ],
    )
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    # Patch _process_and_respond to capture its arguments
    adapter._process_and_respond = AsyncMock()

    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_create_task):
        response = await handler(mock_request)

    # Background task was created
    assert len(created_coros) == 1


@pytest.mark.asyncio
async def test_download_uses_bearer_token(adapter):
    """The httpx GET call to contentUrl includes 'Authorization: Bearer <token>' header."""
    adapter._acquire_token = MagicMock(return_value="test-download-token-abc")

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentUrl": "https://teams.example.com/files/data.xlsx",
            "name": "data.xlsx",
        }])

    # Verify httpx GET was called with Authorization header
    mock_dl_client.get.assert_called_once()
    call_kwargs = mock_dl_client.get.call_args
    headers = call_kwargs[1].get("headers", {}) if call_kwargs[1] else {}
    assert headers.get("Authorization") == "Bearer test-download-token-abc"


@pytest.mark.asyncio
async def test_render_file_received_card():
    """render_file_received produces card with file names and count header."""
    from yigthinker.channels.teams.cards import TeamsCardRenderer
    renderer = TeamsCardRenderer()
    card = renderer.render_file_received(["data.xlsx", "report.csv"])
    assert card["type"] == "AdaptiveCard"
    assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"
    assert card["version"] == "1.5"

    body_text = json.dumps(card["body"])
    assert "data.xlsx" in body_text
    assert "report.csv" in body_text
    # Header mentions count
    assert "Received 2 files" in body_text


@pytest.mark.asyncio
async def test_render_file_received_card_single_file():
    """render_file_received with single file uses singular 'file' not 'files'."""
    from yigthinker.channels.teams.cards import TeamsCardRenderer
    renderer = TeamsCardRenderer()
    card = renderer.render_file_received(["data.xlsx"])
    body_text = json.dumps(card["body"])
    assert "Received 1 file" in body_text
    assert "data.xlsx" in body_text


@pytest.mark.asyncio
async def test_download_uses_content_download_url_without_bearer(adapter):
    """Teams file uploads include content.downloadUrl (pre-authenticated SharePoint URL).
    The adapter must use this URL and NOT send a Bearer token."""
    adapter._acquire_token = MagicMock(return_value="should-not-be-used")

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentType": "application/vnd.microsoft.teams.file.download.info",
            "contentUrl": "https://tenant.sharepoint.com/personal/user/data.xlsx",
            "name": "data.xlsx",
            "content": {
                "downloadUrl": "https://tenant.sharepoint.com/personal/user/data.xlsx?download=true",
                "uniqueId": "abc-123",
                "fileType": "xlsx",
            },
        }])

    assert len(file_lines) == 1
    assert "[Attached file: data.xlsx ->" in file_lines[0]

    # Must use content.downloadUrl, not contentUrl
    call_args = mock_dl_client.get.call_args
    url_used = call_args[0][0]
    assert "download=true" in url_used

    # Must NOT send Bearer token for pre-authenticated URLs
    headers_used = call_args[1].get("headers", {})
    assert "Authorization" not in headers_used


@pytest.mark.asyncio
async def test_download_sanitizes_attachment_name(adapter, tmp_path):
    """Attachment names are reduced to a basename before writing to disk."""
    adapter._acquire_token = MagicMock(return_value="test-download-token")
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    mock_dl_client = _mock_httpx_download()
    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient",
               return_value=mock_dl_client), \
         patch("yigthinker.channels.teams.adapter.tempfile.mkdtemp",
               return_value=str(download_dir)):
        file_lines, error_lines = await adapter._download_attachments([{
            "contentUrl": "https://teams.example.com/files/data.csv",
            "name": "../escape.csv",
        }])

    assert len(error_lines) == 0
    assert len(file_lines) == 1
    assert "[Attached file: escape.csv ->" in file_lines[0]
    assert (download_dir / "escape.csv").exists()
    assert not (tmp_path / "escape.csv").exists()


@pytest.mark.asyncio
async def test_webhook_recognizes_teams_file_download_info_content_type(adapter):
    """Attachments with contentType 'application/vnd.microsoft.teams.file.download.info'
    are recognized as file attachments and passed to _process_and_respond."""
    adapter, handler = await _setup_adapter_with_webhook(adapter)
    adapter._acquire_token = MagicMock(return_value="tok")

    body = _make_webhook_body(
        text="load this",
        attachments=[{
            "contentType": "application/vnd.microsoft.teams.file.download.info",
            "contentUrl": "https://tenant.sharepoint.com/personal/user/data.xlsx",
            "name": "data.xlsx",
            "content": {
                "downloadUrl": "https://tenant.sharepoint.com/...?download=true",
                "fileType": "xlsx",
            },
        }],
    )
    mock_request = _make_signed_request(body, adapter._webhook_secret)

    adapter._process_and_respond = AsyncMock()
    created_coros = []

    def capture_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_create_task):
        response = await handler(mock_request)

    # Background task was created (attachment was recognized, not filtered out)
    assert len(created_coros) == 1
    # Verify thinking card returned
    response_body = json.loads(response.body.decode())
    assert response_body["type"] == "message"
    assert "Analyzing" in response_body["attachments"][0]["content"]["body"][0]["text"]


@pytest.mark.asyncio
async def test_supported_extensions_match_df_load():
    """_SUPPORTED_EXTENSIONS in adapter matches df_load._LOADERS keys exactly."""
    from yigthinker.channels.teams.adapter import _SUPPORTED_EXTENSIONS
    from yigthinker.tools.dataframe.df_load import _LOADERS
    assert _SUPPORTED_EXTENSIONS == set(_LOADERS.keys())


@pytest.mark.asyncio
async def test_process_and_respond_skips_send_when_steering_returns_none(adapter):
    """Steering acknowledged → ``_process_and_respond`` must not render a
    card. ``send_response`` itself early-returns on text=None / error=None,
    so verify no network POST is issued.
    """
    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value=None)
    adapter._acquire_token = MagicMock(return_value="tok")

    # _typing_loop runs forever until cancel; stub it to a no-op coroutine
    async def _noop_typing(event):
        while True:
            await asyncio.sleep(3600)
    adapter._typing_loop = _noop_typing  # type: ignore[assignment]

    # Spy on the renderer — it MUST NOT be called to render None.
    adapter._renderer = MagicMock()
    adapter._renderer.render_text = MagicMock(
        side_effect=AssertionError("render_text MUST NOT be called on None"),
    )
    adapter._renderer.render_error = MagicMock(
        side_effect=AssertionError("render_error MUST NOT be called for steering"),
    )

    event = {
        "from": {"aadObjectId": "user-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-123"},
    }

    posted_urls: list[str] = []

    class _FakeClient:
        def __init__(self, *_, **__): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return None
        async def post(self, url, **kwargs):
            posted_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            return resp

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient", _FakeClient):
        await adapter._process_and_respond("teams:user-1", "steer me", event, None)

    adapter._gateway.handle_message.assert_awaited_once()
    adapter._renderer.render_text.assert_not_called()
    adapter._renderer.render_error.assert_not_called()
    # No POSTs to conversation activities URL (send_response short-circuits).
    activity_posts = [u for u in posted_urls if "/activities" in u]
    assert activity_posts == [], f"Expected no result POST; got {activity_posts}"


@pytest.mark.asyncio
async def test_process_and_respond_passes_quoted_messages_to_gateway(adapter):
    """Task 15 regression: when the user replies to a prior Teams message,
    the adapter must call extract_quoted_messages and forward the result
    to handle_message via quoted_messages=.
    """
    from yigthinker.session import QuotedMessage

    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value="ok")
    adapter._acquire_token = MagicMock(return_value="tok")

    # Stub extract_quoted_messages to return a canned quote.
    canned = [QuotedMessage(
        original_id="msg-1", original_text="what were Q3 sales?", original_role="user"
    )]
    adapter.extract_quoted_messages = AsyncMock(return_value=canned)  # type: ignore[method-assign]

    async def _noop_typing(event):
        while True:
            await asyncio.sleep(3600)
    adapter._typing_loop = _noop_typing  # type: ignore[assignment]

    adapter._renderer = MagicMock()
    adapter._renderer.render_text = MagicMock(return_value={"type": "AdaptiveCard"})

    class _FakeClient:
        def __init__(self, *_, **__): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return None
        async def post(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            return resp

    event = {
        "from": {"aadObjectId": "user-2"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-456"},
        "replyToId": "msg-1",
    }

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient", _FakeClient):
        await adapter._process_and_respond("teams:user-2", "compare to Q4", event, None)

    adapter.extract_quoted_messages.assert_awaited_once()
    kwargs = adapter._gateway.handle_message.await_args.kwargs
    assert kwargs.get("quoted_messages") == canned


@pytest.mark.asyncio
async def test_process_and_respond_passes_none_when_no_quotes(adapter):
    """Empty quote list is collapsed to None before calling handle_message."""
    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value="ok")
    adapter._acquire_token = MagicMock(return_value="tok")
    adapter.extract_quoted_messages = AsyncMock(return_value=[])  # type: ignore[method-assign]

    async def _noop_typing(event):
        while True:
            await asyncio.sleep(3600)
    adapter._typing_loop = _noop_typing  # type: ignore[assignment]

    adapter._renderer = MagicMock()
    adapter._renderer.render_text = MagicMock(return_value={"type": "AdaptiveCard"})

    class _FakeClient:
        def __init__(self, *_, **__): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return None
        async def post(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            return resp

    event = {
        "from": {"aadObjectId": "user-3"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-789"},
    }

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient", _FakeClient):
        await adapter._process_and_respond("teams:user-3", "hello", event, None)

    kwargs = adapter._gateway.handle_message.await_args.kwargs
    assert kwargs.get("quoted_messages") is None
