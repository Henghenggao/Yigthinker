"""Tests for SubagentEventMsg protocol message and Gateway broadcasting."""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from yigthinker.presence.gateway.protocol import SubagentEventMsg, to_json_dict


def test_subagent_event_msg_serialization():
    """SubagentEventMsg serializes to dict with type='subagent_event'."""
    msg = SubagentEventMsg(
        subagent_id="sub-001",
        subagent_name="analyst",
        event="spawned",
        detail="Task: Analyze revenue trends",
    )
    d = to_json_dict(msg)

    assert d["type"] == "subagent_event"
    assert d["subagent_id"] == "sub-001"
    assert d["subagent_name"] == "analyst"
    assert d["event"] == "spawned"
    assert d["detail"] == "Task: Analyze revenue trends"


def test_subagent_event_msg_defaults():
    """SubagentEventMsg has sensible defaults."""
    msg = SubagentEventMsg(
        subagent_id="sub-002",
        subagent_name="forecaster",
        event="completed",
    )
    d = to_json_dict(msg)

    assert d["detail"] == ""
    assert d["type"] == "subagent_event"


def test_subagent_event_msg_all_event_types():
    """All lifecycle event types serialize correctly."""
    for event_type in ("spawned", "completed", "failed", "cancelled"):
        msg = SubagentEventMsg(
            subagent_id="sub-003",
            subagent_name="worker",
            event=event_type,
        )
        d = to_json_dict(msg)
        assert d["event"] == event_type


@pytest.mark.asyncio
async def test_on_tool_event_subagent_broadcast(tmp_path, monkeypatch):
    """Gateway _on_tool_event handler creates SubagentEventMsg for subagent_event type."""
    from yigthinker.presence.gateway.server import GatewayServer, _WSClient

    class DummyAuth:
        def __init__(self):
            self.token = "test-token"
        def verify(self, candidate):
            return candidate == self.token

    monkeypatch.setattr("yigthinker.presence.gateway.server.GatewayAuth", DummyAuth)
    settings = {
        "gateway": {
            "idle_timeout_seconds": 3600,
            "max_sessions": 10,
            "hibernate_dir": str(tmp_path / "hibernate"),
            "eviction_interval_seconds": 60,
        },
        "channels": {},
    }
    gateway = GatewayServer(settings)

    # Track messages sent to WS clients
    sent_messages: list[dict] = []
    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock(side_effect=lambda msg: sent_messages.append(msg))
    client = _WSClient(ws=mock_ws)
    client.session_key = "tui:sub-test"
    gateway._ws_clients.append(client)

    class SubagentAgentLoop:
        async def run(self, user_input, ctx, **kwargs):
            on_tool_event = kwargs.get("on_tool_event")
            assert on_tool_event is not None
            # Simulate subagent lifecycle events
            on_tool_event("subagent_event", {
                "subagent_id": "sub-999",
                "subagent_name": "analyst",
                "event": "spawned",
                "detail": "Task: analyze data",
            })
            on_tool_event("subagent_event", {
                "subagent_id": "sub-999",
                "subagent_name": "analyst",
                "event": "completed",
                "detail": "Analysis done",
            })
            return "done"

    gateway._agent_loop = SubagentAgentLoop()
    gateway._pool = None

    result = await gateway.handle_message("tui:sub-test", "spawn analyst", channel="tui")
    assert result == "done"

    # Allow fire-and-forget tasks to complete
    await asyncio.sleep(0.1)

    # Filter for subagent_event messages
    subagent_msgs = [m for m in sent_messages if m.get("type") == "subagent_event"]
    assert len(subagent_msgs) == 2
    assert subagent_msgs[0]["event"] == "spawned"
    assert subagent_msgs[0]["subagent_name"] == "analyst"
    assert subagent_msgs[1]["event"] == "completed"
