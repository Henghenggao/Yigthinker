import pandas as pd
import pytest
from fastapi.testclient import TestClient

from yigthinker.gateway.server import GatewayServer


class DummyAuth:
    def __init__(self) -> None:
        self.token = "test-token"

    def verify(self, candidate: str) -> bool:
        return candidate == self.token


class FakeAgentLoop:
    async def run(self, user_input: str, ctx) -> str:
        ctx.vars.set("revenue", pd.DataFrame({"value": [1, 2, 3]}))
        ctx.messages.append(type("Msg", (), {"role": "assistant", "content": user_input})())
        return f"echo:{user_input}"


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr("yigthinker.gateway.server.GatewayAuth", DummyAuth)
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

    async def fake_start() -> None:
        gateway._agent_loop = FakeAgentLoop()
        gateway._pool = None

    async def fake_stop() -> None:
        return None

    gateway.start = fake_start
    gateway.stop = fake_stop
    return gateway


def test_session_api_requires_auth(server):
    with TestClient(server.app) as client:
        response = client.get("/api/sessions")
    assert response.status_code == 401


def test_health_endpoint(server):
    """GW-01: /health returns status ok with session count and uptime."""
    with TestClient(server.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "active_sessions" in body
    assert "uptime_seconds" in body
    assert isinstance(body["active_sessions"], int)
    assert isinstance(body["uptime_seconds"], (int, float))


def test_create_session_via_api(server):
    with TestClient(server.app) as client:
        response = client.post(
            "/api/sessions",
            json={"key": "tui:user1", "channel": "tui"},
            headers={"Authorization": f"Bearer {server.auth.token}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "tui:user1"
    assert body["channel_origin"] == "tui"


def test_websocket_round_trip_and_vars_update(server):
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": server.auth.token})
            assert ws.receive_json()["ok"] is True

            ws.send_json({"type": "attach", "session_key": "tui:user1"})
            session_list = ws.receive_json()
            assert session_list["type"] == "session_list"

            ws.send_json({"type": "user_input", "text": "hello", "request_id": "r1"})
            first = ws.receive_json()
            second = ws.receive_json()

    assert {first["type"], second["type"]} == {"vars_update", "response_done"}
    response = first if first["type"] == "response_done" else second
    vars_update = first if first["type"] == "vars_update" else second
    assert response["full_text"] == "echo:hello"
    assert vars_update["vars"][0]["name"] == "revenue"


@pytest.mark.asyncio
async def test_handle_message_restores_hibernated_session(server):
    session = server.registry.get_or_create("tui:user1", {}, "tui")
    session.ctx.vars.set("restored_df", pd.DataFrame({"x": [1]}))
    await server.registry.hibernate("tui:user1")

    class RestoringAgent:
        async def run(self, user_input: str, ctx) -> str:
            assert "restored_df" in ctx.vars
            return f"restored:{user_input}"

    server._agent_loop = RestoringAgent()
    result = await server.handle_message("tui:user1", "resume", channel="tui")
    assert result == "restored:resume"


@pytest.mark.asyncio
async def test_concurrent_messages_serialized(server):
    """GW-04: Per-session lock serializes concurrent messages."""
    import asyncio

    call_order: list[str] = []

    class SlowAgentLoop:
        async def run(self, user_input: str, ctx) -> str:
            call_order.append(f"start:{user_input}")
            await asyncio.sleep(0.05)
            call_order.append(f"end:{user_input}")
            return f"echo:{user_input}"

    server._agent_loop = SlowAgentLoop()

    # Fire two concurrent messages to the SAME session key
    task1 = asyncio.create_task(server.handle_message("test:serial", "msg1", channel="test"))
    task2 = asyncio.create_task(server.handle_message("test:serial", "msg2", channel="test"))
    results = await asyncio.gather(task1, task2)

    assert set(results) == {"echo:msg1", "echo:msg2"}

    # If serialized, we should see start:X end:X start:Y end:Y (not interleaved)
    # The first two entries should be start then end of the same message
    assert call_order[0].startswith("start:")
    assert call_order[1].startswith("end:")
    first_msg = call_order[0].split(":")[1]
    assert call_order[1] == f"end:{first_msg}"
