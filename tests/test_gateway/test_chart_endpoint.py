"""Tests for real chart endpoints mounted by ``GatewayServer._mount_routes()``.

These tests instantiate a real ``GatewayServer`` so that regressions to the
actual route handlers at ``yigthinker/gateway/server.py`` are caught. The
chart cache directory is monkeypatched to a ``tmp_path`` so tests never touch
the user's home directory.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import pytest
from fastapi.testclient import TestClient

import yigthinker.presence.gateway.server as server_mod
from yigthinker.presence.gateway.server import GatewayServer, _resolve_chart_path


class _DummyAuth:
    def __init__(self) -> None:
        self.token = "test-token"

    def verify(self, candidate: str) -> bool:
        return candidate == self.token


@pytest.fixture
def server(tmp_path, monkeypatch):
    """Real GatewayServer with routes mounted and CHART_CACHE_DIR pointed at tmp_path."""
    monkeypatch.setattr(server_mod, "GatewayAuth", _DummyAuth)
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
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

    # Chart endpoints don't need the agent loop; skip the real start() which
    # would try to build an LLM provider from (empty) settings.
    async def _noop_start() -> None:
        return None

    async def _noop_stop() -> None:
        return None

    gateway.start = _noop_start  # type: ignore[method-assign]
    gateway.stop = _noop_stop  # type: ignore[method-assign]
    return gateway


@pytest.fixture
def seeded_cache(tmp_path):
    """Seed a fake PNG and a minimal Plotly JSON into the chart cache dir."""
    (tmp_path / "abc123.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (tmp_path / "abc123.json").write_text(go.Figure().to_json())
    return tmp_path


# ── PNG endpoint ──────────────────────────────────────────────────────────


def test_serve_chart_png_returns_image(server, seeded_cache):
    """GW-chart-01: GET /api/charts/{id}.png returns the cached PNG."""
    with TestClient(server.app) as client:
        resp = client.get("/api/charts/abc123.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_serve_chart_png_404_when_missing(server, seeded_cache):
    """GW-chart-02: missing chart id returns 404."""
    with TestClient(server.app) as client:
        resp = client.get("/api/charts/nonexistent.png")
    assert resp.status_code == 404
    assert resp.json() == {"error": "chart not found"}


@pytest.mark.parametrize("odd_id", ["foo..bar", "....", "a..b"])
def test_serve_chart_png_allows_legitimate_ids_with_dots(server, seeded_cache, odd_id):
    """GW-chart-03: chart ids containing ``..`` but resolving within the cache
    dir are not rejected outright — they simply 404 when no such file exists.

    This verifies the path-resolution guard no longer false-positives on
    legitimate ids like ``chart..v2``.
    """
    with TestClient(server.app) as client:
        resp = client.get(f"/api/charts/{odd_id}.png")
    assert resp.status_code == 404
    assert resp.json() == {"error": "chart not found"}


# ── HTML endpoint ─────────────────────────────────────────────────────────


def test_serve_chart_html_returns_html(server, seeded_cache):
    """GW-chart-04: GET /api/charts/{id} returns rendered Plotly HTML."""
    with TestClient(server.app) as client:
        resp = client.get("/api/charts/abc123")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    # Rendered Plotly HTML always contains a <html> root and references plotly.
    assert "<html" in body.lower()
    assert "plotly" in body.lower()


def test_serve_chart_html_404_when_missing(server, seeded_cache):
    """GW-chart-05: missing chart id returns 404 for HTML route."""
    with TestClient(server.app) as client:
        resp = client.get("/api/charts/nonexistent")
    assert resp.status_code == 404
    assert resp.json() == {"error": "chart not found"}


@pytest.mark.parametrize("odd_id", ["foo..bar", "....", "a..b"])
def test_serve_chart_html_allows_legitimate_ids_with_dots(server, seeded_cache, odd_id):
    """GW-chart-06: chart ids containing ``..`` but resolving within the cache
    dir return 404 (not 400) when no such file exists.
    """
    with TestClient(server.app) as client:
        resp = client.get(f"/api/charts/{odd_id}")
    assert resp.status_code == 404
    assert resp.json() == {"error": "chart not found"}


def test_serve_chart_html_500_on_corrupt_json(server, tmp_path):
    """GW-chart-07: corrupt JSON in cache file returns 500 with explanatory body."""
    (tmp_path / "corrupt.json").write_text("not valid json {{{")
    with TestClient(server.app) as client:
        resp = client.get("/api/charts/corrupt")
    assert resp.status_code == 500
    assert resp.json() == {"error": "corrupt chart data"}


# ── Path resolution helper unit tests ─────────────────────────────────────


def test_resolve_chart_path_valid_id(tmp_path, monkeypatch):
    """GW-chart-08: a plain chart id resolves to a path inside the cache dir."""
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
    path = _resolve_chart_path("abc123", ".png")
    assert path is not None
    assert path == (tmp_path / "abc123.png").resolve()


def test_resolve_chart_path_rejects_traversal(tmp_path, monkeypatch):
    """GW-chart-09: ids that resolve outside the cache dir are rejected.

    URL routing typically filters out ``/`` and ``\\``, so exercising the
    helper directly is the most honest way to verify the containment check.
    """
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
    assert _resolve_chart_path("../../etc/passwd", ".png") is None


def test_resolve_chart_path_rejects_nul_byte(tmp_path, monkeypatch):
    """GW-chart-10: NUL bytes in chart ids produce None (ValueError on resolve)."""
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
    assert _resolve_chart_path("foo\x00bar", ".png") is None


def test_resolve_chart_path_allows_legitimate_dots(tmp_path, monkeypatch):
    """GW-chart-11: legitimate ids containing ``..`` (e.g. ``chart..v2``)
    resolve within the cache dir and are accepted.
    """
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
    path = _resolve_chart_path("chart..v2", ".png")
    assert path is not None
    # Must be contained within tmp_path (no escape).
    assert Path(tmp_path).resolve() in path.parents or path.parent == Path(tmp_path).resolve()
