"""Tests for Gateway WebSocket origin validation (Eng Review #2, CRITICAL-1)."""
import json

import pytest
from fastapi.testclient import TestClient

from yigthinker.presence.gateway.server import GatewayServer


class DummyAuth:
    def __init__(self) -> None:
        self.token = "test-token"

    def verify(self, candidate: str) -> bool:
        return candidate == self.token


@pytest.fixture
def gateway_with_origins(tmp_path, monkeypatch):
    """Gateway with custom allowed origins for LAN access."""
    monkeypatch.setattr("yigthinker.presence.gateway.server.GatewayAuth", DummyAuth)
    settings = {
        "gateway": {
            "idle_timeout_seconds": 3600,
            "max_sessions": 10,
            "hibernate_dir": str(tmp_path / "hibernate"),
            "allowed_origins": ["http://192.168.1.100:8766"],
        },
        "channels": {},
    }
    gateway = GatewayServer(settings)

    async def fake_start():
        gateway._agent_loop = None
        gateway._pool = None

    async def fake_stop():
        return None

    gateway.start = fake_start
    gateway.stop = fake_stop
    return gateway


@pytest.fixture
def gateway_default(tmp_path, monkeypatch):
    """Gateway with default localhost-only origins."""
    monkeypatch.setattr("yigthinker.presence.gateway.server.GatewayAuth", DummyAuth)
    settings = {
        "gateway": {
            "idle_timeout_seconds": 3600,
            "max_sessions": 10,
            "hibernate_dir": str(tmp_path / "hibernate"),
        },
        "channels": {},
    }
    gateway = GatewayServer(settings)

    async def fake_start():
        gateway._agent_loop = None
        gateway._pool = None

    async def fake_stop():
        return None

    gateway.start = fake_start
    gateway.stop = fake_stop
    return gateway


def test_gateway_ws_accepts_localhost_origin(gateway_default):
    """WebSocket from localhost origin should be accepted."""
    with TestClient(gateway_default.app) as client:
        with client.websocket_connect("/ws", headers={"origin": "http://localhost:8766"}) as ws:
            # Should get past origin check. Auth will time out but that's fine.
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))
            msg = ws.receive_json()
            assert msg["type"] == "auth_result"
            assert msg["ok"] is True


def test_gateway_ws_accepts_127_origin(gateway_default):
    """WebSocket from 127.0.0.1 origin should be accepted."""
    with TestClient(gateway_default.app) as client:
        with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:8766"}) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))
            msg = ws.receive_json()
            assert msg["type"] == "auth_result"
            assert msg["ok"] is True


def test_gateway_ws_accepts_runtime_port_origin(tmp_path, monkeypatch):
    """WebSocket should accept the configured runtime port, not just 8766."""
    monkeypatch.setattr("yigthinker.presence.gateway.server.GatewayAuth", DummyAuth)
    settings = {
        "gateway": {
            "idle_timeout_seconds": 3600,
            "max_sessions": 10,
            "hibernate_dir": str(tmp_path / "hibernate"),
            "port": 9000,
        },
        "channels": {},
    }
    gateway = GatewayServer(settings)

    async def fake_start():
        gateway._agent_loop = None
        gateway._pool = None

    async def fake_stop():
        return None

    gateway.start = fake_start
    gateway.stop = fake_stop

    with TestClient(gateway.app) as client:
        with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:9000"}) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))
            msg = ws.receive_json()
            assert msg["type"] == "auth_result"
            assert msg["ok"] is True


def test_gateway_ws_accepts_no_origin(gateway_default):
    """WebSocket with no Origin header (TUI clients) should be accepted."""
    with TestClient(gateway_default.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))
            msg = ws.receive_json()
            assert msg["type"] == "auth_result"
            assert msg["ok"] is True


def test_gateway_ws_rejects_cross_origin(gateway_default):
    """WebSocket from non-localhost origin should be rejected with 4403."""
    with TestClient(gateway_default.app) as client:
        with pytest.raises(Exception):
            # Cross-origin connection should be closed immediately
            with client.websocket_connect("/ws", headers={"origin": "http://evil.com"}) as ws:
                ws.receive_text()


def test_gateway_ws_accepts_configured_origin(gateway_with_origins):
    """WebSocket from a configured allowed origin should be accepted."""
    with TestClient(gateway_with_origins.app) as client:
        with client.websocket_connect("/ws", headers={"origin": "http://192.168.1.100:8766"}) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))
            msg = ws.receive_json()
            assert msg["type"] == "auth_result"
            assert msg["ok"] is True


def test_gateway_ws_rejects_unconfigured_lan_origin(gateway_with_origins):
    """WebSocket from a LAN origin NOT in the allowed list should be rejected."""
    with TestClient(gateway_with_origins.app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws", headers={"origin": "http://192.168.1.200:8766"}) as ws:
                ws.receive_text()
