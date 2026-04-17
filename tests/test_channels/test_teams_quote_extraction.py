"""Tests for Teams adapter quote extraction via Bot Framework reply-to-id.

See Task 14: extract_quoted_messages() fetches the original message via
Bot Framework REST API when a Teams user replies to a prior message.
"""
from __future__ import annotations

import base64

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.presence.channels.teams.adapter import TeamsAdapter
from yigthinker.session import QuotedMessage


@pytest.fixture
def adapter():
    """TeamsAdapter with test config. client_id acts as the bot identifier."""
    a = TeamsAdapter({
        "tenant_id": "test-tenant",
        "client_id": "bot-app-id",
        "client_secret": "test-secret",
        "webhook_secret": base64.b64encode(b"test-key").decode(),
        "session_scope": "per-sender",
    })
    # Patch _acquire_token so MSAL isn't exercised
    a._acquire_token = MagicMock(return_value="fake-token")  # type: ignore[method-assign]
    return a


def _mock_client(resp_status: int = 200, resp_json: dict | None = None,
                 raise_exc: Exception | None = None):
    """Build a patched httpx.AsyncClient context manager."""
    mock_response = MagicMock()
    mock_response.status_code = resp_status
    mock_response.json = MagicMock(return_value=resp_json or {})

    mock_client = AsyncMock()
    if raise_exc is not None:
        mock_client.get = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_no_reply_to_id_returns_empty(adapter):
    """Event without replyToId short-circuits to empty list (no HTTP call)."""
    event = {"text": "hello", "conversation": {"id": "conv-1"}}
    with patch("httpx.AsyncClient") as mock_cls:
        result = await adapter.extract_quoted_messages(event)
    assert result == []
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_reply_to_bot_message_assigns_assistant_role(adapter):
    """When original from.id == bot's client_id, role is 'assistant'."""
    event = {
        "replyToId": "msg-abc-123",
        "conversation": {"id": "conv-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
    }
    original = {
        "id": "msg-abc-123",
        "text": "here are the Q3 sales numbers",
        "from": {"id": "bot-app-id"},
    }

    with patch("httpx.AsyncClient", return_value=_mock_client(200, original)):
        result = await adapter.extract_quoted_messages(event)

    assert len(result) == 1
    q = result[0]
    assert isinstance(q, QuotedMessage)
    assert q.original_id == "msg-abc-123"
    assert q.original_text == "here are the Q3 sales numbers"
    assert q.original_role == "assistant"


@pytest.mark.asyncio
async def test_reply_to_user_message_assigns_user_role(adapter):
    """When original from.id != bot's client_id, role is 'user'."""
    event = {
        "replyToId": "msg-xyz-456",
        "conversation": {"id": "conv-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
    }
    original = {
        "id": "msg-xyz-456",
        "text": "what were Q3 sales?",
        "from": {"id": "some-other-user"},
    }

    with patch("httpx.AsyncClient", return_value=_mock_client(200, original)):
        result = await adapter.extract_quoted_messages(event)

    assert len(result) == 1
    assert result[0].original_role == "user"
    assert result[0].original_text == "what were Q3 sales?"


@pytest.mark.asyncio
async def test_non_200_returns_empty(adapter):
    """Non-200 response returns empty list (no raised exception)."""
    event = {
        "replyToId": "missing-msg",
        "conversation": {"id": "conv-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(404, {})):
        result = await adapter.extract_quoted_messages(event)
    assert result == []


@pytest.mark.asyncio
async def test_network_exception_returns_empty(adapter):
    """httpx timeout / network error is swallowed, returns empty list."""
    event = {
        "replyToId": "msg-1",
        "conversation": {"id": "conv-1"},
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
    }
    with patch("httpx.AsyncClient",
               return_value=_mock_client(raise_exc=httpx.TimeoutException("slow"))):
        result = await adapter.extract_quoted_messages(event)
    assert result == []


@pytest.mark.asyncio
async def test_missing_service_url_returns_empty(adapter):
    """No serviceUrl in event and no override configured → empty list."""
    # Ensure override is empty
    adapter._service_url_override = ""
    event = {
        "replyToId": "msg-1",
        "conversation": {"id": "conv-1"},
        # no serviceUrl
    }
    with patch("httpx.AsyncClient") as mock_cls:
        result = await adapter.extract_quoted_messages(event)
    assert result == []
    # No HTTP call attempted when we have no service URL
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_service_url_override_used_when_event_lacks_it(adapter):
    """When event has no serviceUrl, fall back to configured override."""
    adapter._service_url_override = "https://private.bot.example.com/"
    event = {
        "replyToId": "msg-ovr",
        "conversation": {"id": "conv-2"},
        # no serviceUrl in event
    }
    original = {"id": "msg-ovr", "text": "hi", "from": {"id": "user-x"}}

    mock_client = _mock_client(200, original)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.extract_quoted_messages(event)

    assert len(result) == 1
    # Verify URL built from override
    call_url = mock_client.get.call_args[0][0]
    assert call_url.startswith("https://private.bot.example.com/v3/conversations/conv-2/")


@pytest.mark.asyncio
async def test_service_url_trailing_slash_handled(adapter):
    """Service URL without trailing slash still produces a valid URL."""
    event = {
        "replyToId": "msg-ts",
        "conversation": {"id": "conv-3"},
        "serviceUrl": "https://smba.trafficmanager.net/amer",  # no trailing /
    }
    original = {"id": "msg-ts", "text": "x", "from": {"id": "u"}}
    mock_client = _mock_client(200, original)
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.extract_quoted_messages(event)

    call_url = mock_client.get.call_args[0][0]
    # Should contain exactly one slash between the base and v3
    assert "/amer/v3/conversations/conv-3/activities/msg-ts" in call_url
    assert "//v3" not in call_url
