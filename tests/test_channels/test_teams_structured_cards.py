from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import yigthinker.gateway.server as server_mod
from yigthinker.channels.teams.adapter import TeamsAdapter


def _make_adapter() -> TeamsAdapter:
    adapter = TeamsAdapter(
        {
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "webhook_secret": "secret",
        }
    )
    adapter._acquire_token = MagicMock(return_value="fake-token")  # type: ignore[method-assign]
    adapter._gateway = SimpleNamespace(
        _settings={"gateway": {"host": "gw.local", "port": 8766}}
    )
    return adapter


@pytest.mark.asyncio
async def test_send_response_renders_chart_card_when_artifact_provided(tmp_path, monkeypatch):
    adapter = _make_adapter()
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path)

    posted_payloads: list[dict] = []

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, json, headers):
            posted_payloads.append(json)
            response = MagicMock()
            response.status_code = 200
            return response

    event = {
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-123"},
    }
    artifact = {
        "kind": "chart",
        "chart_name": "Revenue Bridge",
        "chart_json": "{}",
    }

    with patch("yigthinker.visualization.exporter.ChartExporter.to_png", return_value=b"\x89PNG\r\n\x1a\n"), patch(
        "yigthinker.channels.teams.adapter.httpx.AsyncClient",
        _FakeClient,
    ):
        await adapter.send_response(event, "Analysis complete", artifact=artifact)

    card = posted_payloads[0]["attachments"][0]["content"]
    assert card["body"][1]["type"] == "Image"
    assert card["body"][1]["url"].endswith(".png")
    assert card["body"][-1]["text"] == "Analysis complete"
    assert (tmp_path / next(path.name for path in tmp_path.glob("*.json"))).exists()
    assert (tmp_path / next(path.name for path in tmp_path.glob("*.png"))).exists()


@pytest.mark.asyncio
async def test_send_response_renders_native_table_when_artifact_provided():
    adapter = _make_adapter()

    posted_payloads: list[dict] = []

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, json, headers):
            posted_payloads.append(json)
            response = MagicMock()
            response.status_code = 200
            return response

    event = {
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "conversation": {"id": "conv-456"},
    }
    artifact = {
        "kind": "table",
        "title": "last_query",
        "columns": ["region", "revenue"],
        "rows": [["EU", 100], ["US", 200]],
        "total_rows": 2,
    }

    with patch("yigthinker.channels.teams.adapter.httpx.AsyncClient", _FakeClient):
        await adapter.send_response(event, "2 rows returned", artifact=artifact)

    card = posted_payloads[0]["attachments"][0]["content"]
    assert card["body"][1]["type"] == "Table"
    assert card["body"][1]["rows"][1]["cells"][0]["items"][0]["text"] == "EU"
    assert card["body"][-1]["text"] == "2 rows returned"
