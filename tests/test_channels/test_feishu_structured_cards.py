from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yigthinker.presence.channels.feishu.adapter import FeishuAdapter
from yigthinker.session import QuotedMessage


def _make_adapter() -> FeishuAdapter:
    adapter = FeishuAdapter(
        {
            "app_id": "test-app",
            "app_secret": "test-secret",
            "verification_token": "",
            "session_scope": "per-sender",
        }
    )
    adapter._dedup = MagicMock()
    adapter._dedup.is_duplicate = MagicMock(return_value=False)
    adapter._dedup.record = MagicMock()
    adapter._client = MagicMock()
    return adapter


def _text_event(text: str = "hello") -> dict:
    return {
        "header": {"event_id": "evt-1"},
        "event": {
            "sender": {"sender_id": {"open_id": "user-1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


@pytest.mark.asyncio
async def test_process_event_renders_vchart_card_when_chart_artifact_present():
    adapter = _make_adapter()

    async def _fake_handle_message(key, text, **kwargs):
        on_tool_event = kwargs.get("on_tool_event")
        assert on_tool_event is not None
        on_tool_event(
            "tool_result",
            {
                "tool_id": "tool-1",
                "content": '{"chart_name":"Revenue","chart_json":"{}"}',
                "content_obj": {
                    "chart_name": "Revenue",
                    "chart_json": "{}",
                },
                "is_error": False,
            },
        )
        return "Analysis complete"

    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(side_effect=_fake_handle_message)

    send_calls: list[tuple[str, dict]] = []
    update_calls: list[tuple[str, dict]] = []

    async def fake_send(receive_id, card):
        send_calls.append((receive_id, card))
        return "thinking-msg-id"

    async def fake_update(message_id, card):
        update_calls.append((message_id, card))

    adapter._send_card = fake_send  # type: ignore[assignment]
    adapter._update_card = fake_update  # type: ignore[assignment]

    with patch(
        "yigthinker.visualization.exporter.ChartExporter.to_vchart",
        return_value={"type": "common", "series": [], "data": [{"values": []}]},
    ):
        await adapter._process_event(_text_event("show me the chart"))

    assert len(send_calls) == 1
    assert len(update_calls) == 1
    card = update_calls[0][1]
    assert card["elements"][0]["tag"] == "chart"
    assert card["elements"][0]["chart_spec"]["type"] == "vchart"
    assert any(
        element.get("tag") == "markdown" and element.get("content") == "Analysis complete"
        for element in card["elements"]
    )


@pytest.mark.asyncio
async def test_process_event_passes_quoted_messages_to_gateway():
    adapter = _make_adapter()
    adapter._gateway = MagicMock()
    adapter._gateway.handle_message = AsyncMock(return_value="ok")

    canned = [QuotedMessage(original_id="msg-1", original_text="compare to the prior answer")]
    adapter.extract_quoted_messages = AsyncMock(return_value=canned)  # type: ignore[method-assign]

    async def fake_send(receive_id, card):
        return "thinking-msg-id"

    async def fake_update(message_id, card):
        return None

    adapter._send_card = fake_send  # type: ignore[assignment]
    adapter._update_card = fake_update  # type: ignore[assignment]

    await adapter._process_event(_text_event("follow up"))

    kwargs = adapter._gateway.handle_message.await_args.kwargs
    assert kwargs.get("quoted_messages") == canned


@pytest.mark.asyncio
async def test_send_response_renders_native_table_when_artifact_provided():
    adapter = _make_adapter()
    adapter._send_card = AsyncMock(return_value="msg-1")  # type: ignore[assignment]

    event = _text_event("show table")
    artifact = {
        "kind": "table",
        "title": "last_query",
        "columns": ["region", "revenue"],
        "rows": [["EU", 100], ["US", 200]],
        "total_rows": 2,
    }

    await adapter.send_response(event, "2 rows returned", artifact=artifact)

    card = adapter._send_card.await_args.args[1]
    assert card["elements"][0]["tag"] == "table"
    assert card["elements"][0]["rows"][0] == {"region": "EU", "revenue": 100}
    assert card["elements"][-1]["content"] == "2 rows returned"
