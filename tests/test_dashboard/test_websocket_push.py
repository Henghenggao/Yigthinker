import pytest
from unittest.mock import AsyncMock, patch
from yigthinker.dashboard.websocket_client import DashboardClient


async def test_push_calls_server_api():
    client = DashboardClient(server_url="http://localhost:8765")

    with patch("yigthinker.dashboard.websocket_client._http_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"ok": True, "dashboard_id": "abc"}
        result = await client.push(
            dashboard_id="abc",
            title="My Chart",
            chart_json='{"data":[],"layout":{}}',
        )

    mock_post.assert_called_once()
    assert result["ok"] is True


async def test_push_silently_fails_when_no_server():
    client = DashboardClient(server_url="http://localhost:19999")
    result = await client.push(dashboard_id="x", title="x", chart_json="{}")
    assert result is None
