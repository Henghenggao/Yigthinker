"""Tests for Feishu adapter — focus on steering acknowledgement (None result).

The full webhook signing / card round-trip is exercised elsewhere; these
tests pin down the behaviour around ``handle_message`` returning ``None``
when a live-steering message was enqueued on a running agent.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from yigthinker.channels.feishu.adapter import FeishuAdapter


def _make_adapter() -> FeishuAdapter:
    adapter = FeishuAdapter({
        "app_id": "test-app",
        "app_secret": "test-secret",
        "verification_token": "",
        "session_scope": "per-sender",
    })
    # Avoid touching sqlite on disk during unit tests.
    adapter._dedup = MagicMock()
    adapter._dedup.is_duplicate = MagicMock(return_value=False)
    adapter._dedup.record = MagicMock()
    # Pretend the lark client is built — _send_card checks truthiness.
    adapter._client = MagicMock()
    return adapter


def _text_event(text: str = "hello") -> dict:
    import json as _json
    return {
        "header": {"event_id": "evt-1"},
        "event": {
            "sender": {"sender_id": {"open_id": "user-1"}},
            "message": {
                "message_type": "text",
                "content": _json.dumps({"text": text}),
            },
        },
    }


@pytest.mark.asyncio
async def test_process_event_skips_response_when_steering_returns_none():
    """When ``handle_message`` returns ``None`` (steering acknowledged), the
    adapter MUST NOT render a second card — the running agent will surface
    the result via its own card update.
    """
    adapter = _make_adapter()
    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value=None)

    # Record calls to _send_card and _update_card
    # (_send_card is invoked once for the "thinking" card, nothing more)
    send_calls: list = []
    update_calls: list = []

    async def fake_send(receive_id, card):
        send_calls.append((receive_id, card))
        return "thinking-msg-id"

    async def fake_update(message_id, card):
        update_calls.append((message_id, card))

    adapter._send_card = fake_send  # type: ignore[assignment]
    adapter._update_card = fake_update  # type: ignore[assignment]

    await adapter._process_event({"event": _text_event("steer me")["event"],
                                  "header": _text_event("steer me")["header"]})

    # Gateway was asked — confirm routing happened
    adapter._gateway.handle_message.assert_awaited_once()

    # Exactly one send_card call — the "thinking" card sent BEFORE
    # the gateway returned None.
    assert len(send_calls) == 1, f"Expected only the thinking card to be sent; got {send_calls}"

    # No follow-up update_card or additional send_card for the result.
    assert update_calls == [], f"Expected no result card update; got {update_calls}"


@pytest.mark.asyncio
async def test_process_event_renders_result_when_handle_message_returns_text():
    """Control: a normal (non-None) result still triggers the card update."""
    adapter = _make_adapter()
    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value="Analysis complete")

    send_calls: list = []
    update_calls: list = []

    async def fake_send(receive_id, card):
        send_calls.append((receive_id, card))
        return "thinking-msg-id"

    async def fake_update(message_id, card):
        update_calls.append((message_id, card))

    adapter._send_card = fake_send  # type: ignore[assignment]
    adapter._update_card = fake_update  # type: ignore[assignment]

    await adapter._process_event(_text_event("real query"))

    adapter._gateway.handle_message.assert_awaited_once()
    assert len(send_calls) == 1  # thinking card
    assert len(update_calls) == 1  # result card update
    assert update_calls[0][0] == "thinking-msg-id"
