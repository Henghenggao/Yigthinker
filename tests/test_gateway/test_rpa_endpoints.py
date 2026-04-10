"""Integration tests for /api/rpa/callback and /api/rpa/report via fastapi TestClient."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from yigthinker.gateway.rpa_controller import RPAController
from yigthinker.gateway.rpa_state import RPAStateStore
from yigthinker.gateway.server import GatewayServer


def _fake_settings() -> dict:
    return {
        "gateway": {
            "host": "127.0.0.1",
            "port": 8766,
            "rpa": {"max_attempts_24h": 3, "max_llm_calls_day": 10},
        },
    }


def _build_server_with_rpa(tmp_path: Path) -> GatewayServer:
    """Build a GatewayServer and manually wire an RPAController (skipping real build_app)."""
    srv = GatewayServer(_fake_settings())
    state = RPAStateStore(db_path=tmp_path / "state.db")
    registry = MagicMock()
    registry.load_index.return_value = {
        "workflows": {
            "wf-a": {
                "status": "active",
                "run_count_30d": 0,
                "failure_count_30d": 0,
                "last_run": None,
            }
        }
    }
    provider = MagicMock()
    provider.chat = AsyncMock()
    srv._rpa_controller = RPAController(state=state, registry=registry, provider=provider)
    return srv


def test_callback_requires_auth(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    with TestClient(srv.app) as client:
        r = client.post("/api/rpa/callback", json={})
    assert r.status_code == 401


def test_report_requires_auth(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    with TestClient(srv.app) as client:
        r = client.post("/api/rpa/report", json={})
    assert r.status_code == 401


def test_callback_503_when_controller_missing(tmp_path: Path) -> None:
    """Before GatewayServer.start() wires _rpa_controller, callback route returns 503."""
    srv = GatewayServer(_fake_settings())
    # Intentionally do NOT set _rpa_controller
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        r = client.post("/api/rpa/callback", json={}, headers=headers)
    assert r.status_code == 503


def test_callback_returns_decision(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    payload = {
        "callback_id": "cb-integration-1",
        "workflow_name": "wf-a",
        "version": 1,
        "checkpoint_id": "ckpt-1",
        "attempt_number": 1,
        "error_type": "ConnectionError",
        "error_message": "refused",
        "traceback": "Traceback...",
        "step_context": {"name": "step_1", "inputs_summary": {}},
    }
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        r = client.post("/api/rpa/callback", json=payload, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "action" in body
    assert "instruction" in body
    assert "reason" in body


def test_callback_dedup(tmp_path: Path) -> None:
    """Same callback_id → same response, stub NOT re-executed (check via decision_json cache)."""
    srv = _build_server_with_rpa(tmp_path)
    payload = {
        "callback_id": "cb-dedup-1",
        "workflow_name": "wf-a",
        "version": 1,
        "checkpoint_id": "ckpt-1",
        "attempt_number": 1,
        "error_type": "ConnectionError",
        "error_message": "x",
        "traceback": "x",
        "step_context": {"name": "s", "inputs_summary": {}},
    }
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        r1 = client.post("/api/rpa/callback", json=payload, headers=headers)
        r2 = client.post("/api/rpa/callback", json=payload, headers=headers)
    assert r1.json() == r2.json()


def test_circuit_breaker_attempts(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}

        def _pl(i: int) -> dict:
            return {
                "callback_id": f"cb-ba-{i}",
                "workflow_name": "wf-b",
                "version": 1,
                "checkpoint_id": "ckpt-same",
                "attempt_number": i + 1,
                "error_type": "ValueError",
                "error_message": "x",
                "traceback": "x",
                "step_context": {"name": "s", "inputs_summary": {}},
            }
        for i in range(3):
            r = client.post("/api/rpa/callback", json=_pl(i), headers=headers)
            assert r.status_code == 200
        r4 = client.post("/api/rpa/callback", json=_pl(3), headers=headers)
    assert r4.json()["reason"] == "breaker_exceeded"


def test_circuit_breaker_llm_cap(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        for i in range(10):
            r = client.post("/api/rpa/callback", json={
                "callback_id": f"cb-llm-{i}",
                "workflow_name": "wf-llm",
                "version": 1,
                "checkpoint_id": f"ckpt-{i}",
                "attempt_number": 1,
                "error_type": "ValueError",
                "error_message": "x",
                "traceback": "x",
                "step_context": {"name": "s", "inputs_summary": {}},
            }, headers=headers)
            assert r.status_code == 200
        r11 = client.post("/api/rpa/callback", json={
            "callback_id": "cb-llm-11",
            "workflow_name": "wf-llm",
            "version": 1,
            "checkpoint_id": "ckpt-11",
            "attempt_number": 1,
            "error_type": "ValueError",
            "error_message": "x",
            "traceback": "x",
            "step_context": {"name": "s", "inputs_summary": {}},
        }, headers=headers)
    assert r11.json()["reason"] == "breaker_exceeded"


def test_report_updates_registry(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    registry = srv._rpa_controller._registry
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        r = client.post("/api/rpa/report", json={
            "workflow_name": "wf-a",
            "version": 1,
            "run_id": "run-1",
            "started_at": "2026-04-10T10:00:00+00:00",
            "finished_at": "2026-04-10T10:05:00+00:00",
            "status": "success",
            "error_summary": None,
        }, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    registry.save_index.assert_called_once()


def test_report_no_llm_call(tmp_path: Path) -> None:
    srv = _build_server_with_rpa(tmp_path)
    provider = srv._rpa_controller._provider
    with TestClient(srv.app) as client:
        headers = {"Authorization": f"Bearer {srv.auth.token}"}
        client.post("/api/rpa/report", json={
            "workflow_name": "wf-a",
            "version": 1,
            "run_id": "run-1",
            "started_at": "2026-04-10T10:00:00+00:00",
            "finished_at": "2026-04-10T10:05:00+00:00",
            "status": "success",
            "error_summary": None,
        }, headers=headers)
    provider.chat.assert_not_called()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="sqlite file handle teardown timing on NTFS can race across TestClient restarts",
)
def test_breaker_persists_across_restart(tmp_path: Path) -> None:
    """Circuit breaker state survives process restart (sqlite durability)."""
    # First server: record 3 attempts
    srv1 = _build_server_with_rpa(tmp_path)
    with TestClient(srv1.app) as client:
        headers = {"Authorization": f"Bearer {srv1.auth.token}"}
        for i in range(3):
            client.post("/api/rpa/callback", json={
                "callback_id": f"cb-r-{i}",
                "workflow_name": "wf-persist",
                "version": 1,
                "checkpoint_id": "ckpt-persist",
                "attempt_number": 1,
                "error_type": "ValueError",
                "error_message": "x",
                "traceback": "x",
                "step_context": {"name": "s", "inputs_summary": {}},
            }, headers=headers)
    srv1._rpa_controller._state.close()

    # Second server: same db_path → 4th attempt should trip breaker
    srv2 = GatewayServer(_fake_settings())
    state2 = RPAStateStore(db_path=tmp_path / "state.db")
    registry2 = MagicMock()
    registry2.load_index.return_value = {"workflows": {}}
    provider2 = MagicMock()
    provider2.chat = AsyncMock()
    srv2._rpa_controller = RPAController(state=state2, registry=registry2, provider=provider2)
    with TestClient(srv2.app) as client:
        headers = {"Authorization": f"Bearer {srv2.auth.token}"}
        r = client.post("/api/rpa/callback", json={
            "callback_id": "cb-r-4",
            "workflow_name": "wf-persist",
            "version": 1,
            "checkpoint_id": "ckpt-persist",
            "attempt_number": 4,
            "error_type": "ValueError",
            "error_message": "x",
            "traceback": "x",
            "step_context": {"name": "s", "inputs_summary": {}},
        }, headers=headers)
    assert r.json()["reason"] == "breaker_exceeded"
    state2.close()
