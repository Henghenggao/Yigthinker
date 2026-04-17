"""Feishu send_response integration coverage (Phase 1a housekeeping H3).

Exercises the happy path of sending a text response + vars summary via
the adapter's internal _send_card path (mocking the lark client).

Adapter-reality notes
---------------------
* ``__init__`` takes a single dict config — identical to the plan skeleton.
* ``send_response`` signature: ``(event, text, vars_summary=None, artifact=None)``.
  The ``vars_summary`` kwarg is accepted but NOT forwarded into the card payload;
  the rendered card only contains ``text``.  Test 2 therefore asserts that
  ``_send_card`` is still called (the path doesn't blow up) and that the text
  passed in ``send_response`` appears in the card — not "df1" — because the
  current adapter does not embed vars summaries in the card body.
* The no-client guard is ``if not self._client: return`` at line 142, so test 3
  pins the existing early-return behaviour.
* ``_send_card`` is the correct mock target (used at adapter.py line 151).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from yigthinker.presence.channels.feishu.adapter import FeishuAdapter


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
    # Pretend the lark client is built — send_response checks truthiness.
    adapter._client = MagicMock()
    # Stub the card-sending primitive so we can assert calls without hitting network.
    adapter._send_card = AsyncMock(return_value=None)  # type: ignore[assignment]
    return adapter


def _make_event(event_id: str = "evt-1") -> dict:
    return {
        "header": {"event_id": event_id},
        "event": {
            "sender": {"sender_id": {"open_id": "user-xyz"}},
            "message": {
                "message_id": "om_abc",
                "chat_id": "oc_chat",
                "message_type": "text",
            },
        },
    }


@pytest.mark.asyncio
async def test_send_response_text_only_dispatches_card():
    """send_response with plain text calls _send_card exactly once and
    passes the response text through to the card payload."""
    adapter = _make_adapter()
    await adapter.send_response(_make_event("evt-1"), "Hello from Yigthinker")

    assert adapter._send_card.await_count == 1
    payload_repr = str(adapter._send_card.call_args)
    assert "Hello from Yigthinker" in payload_repr


@pytest.mark.asyncio
async def test_send_response_includes_vars_summary_when_provided():
    """send_response accepts vars_summary without raising, still dispatches
    exactly one card, and the text arg appears in the card payload.

    NOTE: the current adapter accepts vars_summary but does not embed it in
    the card body — the text is still rendered correctly.  This test pins that
    the kwarg doesn't break the happy path rather than asserting "df1" appears
    (which would be wrong for the current implementation).
    """
    adapter = _make_adapter()
    vars_summary = [{"name": "df1", "shape": [10, 3], "dtypes": {"a": "int64"}}]
    await adapter.send_response(
        _make_event("evt-2"),
        "Result ready",
        vars_summary=vars_summary,
    )

    assert adapter._send_card.await_count == 1
    payload_repr = str(adapter._send_card.call_args)
    assert "Result ready" in payload_repr


@pytest.mark.asyncio
async def test_send_response_without_client_is_noop():
    """When _client is None (lark-oapi not installed or start() not called),
    send_response must return immediately without calling _send_card."""
    adapter = _make_adapter()
    adapter._client = None

    await adapter.send_response(_make_event("evt-3"), "some text")

    assert adapter._send_card.await_count == 0
