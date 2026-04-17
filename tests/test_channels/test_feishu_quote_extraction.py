from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from yigthinker.presence.channels.feishu.adapter import FeishuAdapter
from yigthinker.session import QuotedMessage


def _make_adapter() -> FeishuAdapter:
    adapter = FeishuAdapter(
        {
            "app_id": "app-123",
            "app_secret": "secret-123",
            "verification_token": "",
            "session_scope": "per-sender",
        }
    )
    adapter._dedup = MagicMock()
    adapter._client = MagicMock()
    return adapter


def _response(items, success: bool = True):
    return SimpleNamespace(
        success=lambda: success,
        data=SimpleNamespace(items=items),
    )


@pytest.mark.asyncio
async def test_extract_quoted_messages_returns_empty_without_linkage_ids():
    adapter = _make_adapter()
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "content": '{"text":"hello"}',
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)
    assert result == []
    adapter._client.im.v1.message.get.assert_not_called()


@pytest.mark.asyncio
async def test_extract_quoted_messages_fetches_parent_message_as_user():
    adapter = _make_adapter()
    adapter._client.im.v1.message.get.return_value = _response(
        [
            SimpleNamespace(
                body=SimpleNamespace(content='{"text":"what were Q3 sales?"}'),
                sender=SimpleNamespace(id="ou_user_1", sender_type="user"),
            )
        ]
    )
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "parent_id": "msg-parent",
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)

    assert len(result) == 1
    quoted = result[0]
    assert isinstance(quoted, QuotedMessage)
    assert quoted.original_id == "msg-parent"
    assert quoted.original_text == "what were Q3 sales?"
    assert quoted.original_role == "user"


@pytest.mark.asyncio
async def test_extract_quoted_messages_marks_app_sender_as_assistant():
    adapter = _make_adapter()
    adapter._client.im.v1.message.get.return_value = _response(
        [
            SimpleNamespace(
                body=SimpleNamespace(content='{"text":"here is the prior answer"}'),
                sender=SimpleNamespace(id="app-123", sender_type="app"),
            )
        ]
    )
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "upper_message_id": "msg-upper",
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)

    assert len(result) == 1
    assert result[0].original_role == "assistant"
    assert result[0].original_id == "msg-upper"


@pytest.mark.asyncio
async def test_extract_quoted_messages_falls_back_to_root_id():
    adapter = _make_adapter()
    adapter._client.im.v1.message.get.return_value = _response(
        [
            SimpleNamespace(
                body=SimpleNamespace(content='{"text":"thread root"}'),
                sender=SimpleNamespace(id="ou_user_2", sender_type="user"),
            )
        ]
    )
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "root_id": "msg-root",
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)
    assert len(result) == 1
    assert result[0].original_id == "msg-root"
    assert result[0].original_text == "thread root"


@pytest.mark.asyncio
async def test_extract_quoted_messages_returns_empty_on_unsuccessful_response():
    adapter = _make_adapter()
    adapter._client.im.v1.message.get.return_value = _response([], success=False)
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "parent_id": "msg-parent",
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)
    assert result == []


@pytest.mark.asyncio
async def test_extract_quoted_messages_falls_back_to_raw_content_when_not_json():
    adapter = _make_adapter()
    adapter._client.im.v1.message.get.return_value = _response(
        [
            SimpleNamespace(
                body=SimpleNamespace(content="plain text body"),
                sender=SimpleNamespace(id="ou_user_3", sender_type="user"),
            )
        ]
    )
    event = {
        "event": {
            "message": {
                "message_id": "msg-current",
                "parent_id": "msg-parent",
            }
        }
    }

    result = await adapter.extract_quoted_messages(event)
    assert len(result) == 1
    assert result[0].original_text == "plain text body"
