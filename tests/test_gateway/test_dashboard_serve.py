"""Tests for Gateway dashboard static file serving (Eng Review #2, CRITICAL-2)."""
import pytest
from fastapi.testclient import TestClient

from yigthinker.gateway.server import GatewayServer


class DummyAuth:
    def __init__(self) -> None:
        self.token = "test-token"

    def verify(self, candidate: str) -> bool:
        return candidate == self.token


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setattr("yigthinker.gateway.server.GatewayAuth", DummyAuth)
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


def test_dashboard_index_html(gateway):
    """GET /dashboard/ returns the dashboard HTML page."""
    with TestClient(gateway.app) as client:
        response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Yigthinker" in response.text


def test_dashboard_root_redirect(gateway):
    """GET /dashboard returns the same page (no trailing slash)."""
    with TestClient(gateway.app) as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Yigthinker" in response.text


def test_dashboard_spa_fallback(gateway):
    """GET /dashboard/settings returns index.html (SPA routing)."""
    with TestClient(gateway.app) as client:
        response = client.get("/dashboard/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Yigthinker" in response.text


def test_dashboard_static_css(gateway):
    """GET /dashboard/assets/styles.css returns CSS."""
    with TestClient(gateway.app) as client:
        response = client.get("/dashboard/assets/styles.css")
    assert response.status_code == 200
    assert "--bg-primary" in response.text


def test_dashboard_static_js(gateway):
    """GET /dashboard/assets/app.js returns JavaScript."""
    with TestClient(gateway.app) as client:
        response = client.get("/dashboard/assets/app.js")
    assert response.status_code == 200
    assert "WebSocket" in response.text
