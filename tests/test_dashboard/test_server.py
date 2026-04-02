import json

from fastapi.testclient import TestClient

from yigthinker.dashboard.server import DashboardSessionBridge, create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_entries_empty():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/dashboard/entries")
    assert response.status_code == 200
    assert response.json() == []


def test_push_entry():
    app = create_app()
    client = TestClient(app)
    payload = {
        "dashboard_id": "abc123",
        "title": "Revenue Chart",
        "chart_json": '{"data":[],"layout":{}}',
    }
    response = client.post("/api/dashboard/push", json=payload)
    assert response.status_code == 200

    entries = client.get("/api/dashboard/entries").json()
    assert len(entries) == 1
    assert entries[0]["title"] == "Revenue Chart"


def test_drilldown_routes_to_active_session():
    bridge = DashboardSessionBridge()

    async def handler(prompt: str) -> str:
        return f"handled: {prompt}"

    token = bridge.register_session("session-1", handler)
    app = create_app(session_bridge=bridge)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"
        ws.send_text(json.dumps({
            "type": "drilldown",
            "session_id": "session-1",
            "prompt": "North region",
            "token": token,
        }))
        result = ws.receive_json()

    assert result["type"] == "drilldown_result"
    assert result["result"] == "handled: North region"


def test_drilldown_rejected_without_token():
    bridge = DashboardSessionBridge()

    async def handler(prompt: str) -> str:
        return "should not reach"

    bridge.register_session("session-1", handler)
    app = create_app(session_bridge=bridge)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # init
        ws.send_text(json.dumps({
            "type": "drilldown",
            "session_id": "session-1",
            "prompt": "malicious",
        }))
        result = ws.receive_json()

    assert result["type"] == "drilldown_error"
    assert "token" in result["message"].lower()


def test_drilldown_rejected_with_wrong_token():
    bridge = DashboardSessionBridge()

    async def handler(prompt: str) -> str:
        return "should not reach"

    bridge.register_session("session-1", handler)
    app = create_app(session_bridge=bridge)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # init
        ws.send_text(json.dumps({
            "type": "drilldown",
            "session_id": "session-1",
            "prompt": "malicious",
            "token": "wrong-token",
        }))
        result = ws.receive_json()

    assert result["type"] == "drilldown_error"
