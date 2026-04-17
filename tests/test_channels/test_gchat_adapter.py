"""Tests for Google Chat adapter — focus on steering acknowledgement (None result).

When ``handle_message`` returns ``None`` the adapter must NOT invoke
``render_text(None)`` — that would produce a broken card. Instead the
webhook responds with an empty message.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from yigthinker.presence.channels.gchat.adapter import GChatAdapter


def _make_adapter() -> GChatAdapter:
    return GChatAdapter({
        "session_scope": "per-sender",
        "project_number": "",
    })


async def _install_webhook(adapter: GChatAdapter) -> callable:
    """Start the adapter with a FastAPI-like mock and capture the webhook."""
    route_handler = None

    def capture_post(path):
        def decorator(fn):
            nonlocal route_handler
            route_handler = fn
            return fn
        return decorator

    mock_gateway = MagicMock()
    mock_gateway.app = MagicMock()
    mock_gateway.app.post = capture_post
    adapter._gateway = mock_gateway
    await adapter.start(mock_gateway)
    assert route_handler is not None
    return route_handler, mock_gateway


def _message_event(text: str = "hello") -> dict:
    return {
        "type": "MESSAGE",
        "message": {"text": text, "argumentText": text},
        "user": {"name": "users/u1"},
        "space": {"name": "spaces/AAA"},
    }


def _mock_request(body: dict):
    req = AsyncMock()
    req.json = AsyncMock(return_value=body)
    req.headers = {"authorization": "Bearer ignored"}
    return req


@pytest.mark.asyncio
async def test_webhook_skips_render_when_handle_message_returns_none():
    """Steering acknowledged → adapter returns empty-text JSON and does NOT
    call ``render_text(None)``."""
    adapter = _make_adapter()
    route_handler, gateway = await _install_webhook(adapter)
    gateway.handle_message = AsyncMock(return_value=None)

    # Bypass JWT check (project_number is empty → verify returns False).
    # Patch _verify_gchat_token to allow the request.
    with patch(
        "yigthinker.presence.channels.gchat.adapter._verify_gchat_token",
        return_value=True,
    ):
        # Replace renderer with a spy that would raise if called on None
        adapter._renderer = MagicMock()
        adapter._renderer.render_text = MagicMock(
            side_effect=AssertionError("render_text MUST NOT be called on None"),
        )

        response: JSONResponse = await route_handler(_mock_request(_message_event("steer me")))

    import json as _json
    body = _json.loads(response.body.decode())
    assert body == {"text": ""}, f"Expected empty-text response; got {body}"

    # render_text was never invoked (the AssertionError side_effect confirms)
    adapter._renderer.render_text.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_renders_card_when_handle_message_returns_text():
    """Control: non-None result flows through render_text normally."""
    adapter = _make_adapter()
    route_handler, gateway = await _install_webhook(adapter)
    gateway.handle_message = AsyncMock(return_value="Analysis complete")

    with patch(
        "yigthinker.presence.channels.gchat.adapter._verify_gchat_token",
        return_value=True,
    ):
        adapter._renderer = MagicMock()
        adapter._renderer.render_text = MagicMock(return_value={"text": "Analysis complete"})

        response: JSONResponse = await route_handler(_mock_request(_message_event("real query")))

    adapter._renderer.render_text.assert_called_once_with("Analysis complete")
    import json as _json
    body = _json.loads(response.body.decode())
    assert body == {"text": "Analysis complete"}
