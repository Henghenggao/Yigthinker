import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def chart_cache(tmp_path, monkeypatch):
    """Point CHART_CACHE_DIR at a tmp dir and seed a fake PNG + fig JSON."""
    import yigthinker.gateway.server as server_mod
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)
    # Seed a valid PNG
    (tmp_path / "abc123.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    # Seed a minimal Plotly JSON
    import plotly.graph_objects as go
    (tmp_path / "abc123.json").write_text(go.Figure().to_json())
    return tmp_path


def test_serve_chart_png_returns_image(chart_cache, monkeypatch):
    """GET /api/charts/{id}.png returns the cached PNG."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI()

    @app.get("/api/charts/{chart_id}.png")
    async def serve_chart_image(chart_id: str):
        path = chart_cache / f"{chart_id}.png"
        if not path.exists():
            return JSONResponse({"error": "chart not found"}, status_code=404)
        return FileResponse(path, media_type="image/png")

    client = TestClient(app)
    resp = client.get("/api/charts/abc123.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_serve_chart_png_404_when_missing(chart_cache):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI()

    @app.get("/api/charts/{chart_id}.png")
    async def serve_chart_image(chart_id: str):
        path = chart_cache / f"{chart_id}.png"
        if not path.exists():
            return JSONResponse({"error": "chart not found"}, status_code=404)
        return FileResponse(path, media_type="image/png")

    client = TestClient(app)
    resp = client.get("/api/charts/nonexistent.png")
    assert resp.status_code == 404
