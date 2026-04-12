"""Tests for pa_list_connections tool handler (Plan 12-05 RED/GREEN).

Happy path + filtered + empty list per D-23/D-25.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from yigthinker_mcp_powerautomate.tools.pa_list_connections import (
    PaListConnectionsInput,
    handle as handle_connections,
)

pytestmark = pytest.mark.asyncio


async def test_happy_path_returns_connections() -> None:
    """Returns mapped list of connection summaries."""
    client = AsyncMock()
    client.list_connections.return_value = [
        {
            "name": "conn-001",
            "properties": {
                "displayName": "Office 365 Outlook",
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
                "statuses": [{"status": "Connected"}],
            },
        },
        {
            "name": "conn-002",
            "properties": {
                "displayName": "SQL Server",
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_sql",
                "statuses": [{"status": "Error"}],
            },
        },
    ]

    result = await handle_connections(
        PaListConnectionsInput(
            environment_id="env-001",
        ),
        client,
    )

    assert result["environment_id"] == "env-001"
    assert len(result["connections"]) == 2
    assert result["connections"][0]["connection_id"] == "conn-001"
    assert result["connections"][0]["display_name"] == "Office 365 Outlook"
    assert result["connections"][0]["connector"] == (
        "/providers/Microsoft.PowerApps/apis/shared_office365"
    )
    assert result["connections"][0]["statuses"] == [{"status": "Connected"}]
    assert result["connections"][1]["connection_id"] == "conn-002"
    client.list_connections.assert_awaited_once_with("env-001", None)


async def test_filtered_by_connector_name() -> None:
    """Passes connector_name through to client."""
    client = AsyncMock()
    client.list_connections.return_value = [
        {
            "name": "conn-003",
            "properties": {
                "displayName": "SharePoint",
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                "statuses": [],
            },
        },
    ]

    result = await handle_connections(
        PaListConnectionsInput(
            environment_id="env-002",
            connector_name="shared_sharepointonline",
        ),
        client,
    )

    assert len(result["connections"]) == 1
    assert result["connections"][0]["connection_id"] == "conn-003"
    client.list_connections.assert_awaited_once_with(
        "env-002", "shared_sharepointonline",
    )


async def test_empty_connections_list() -> None:
    """Empty connections returns empty array."""
    client = AsyncMock()
    client.list_connections.return_value = []

    result = await handle_connections(
        PaListConnectionsInput(environment_id="env-003"),
        client,
    )

    assert result["environment_id"] == "env-003"
    assert result["connections"] == []


async def test_http_error_returns_error_dict() -> None:
    """HTTPStatusError is caught and returned as an is_error dict."""
    request = httpx.Request("GET", "https://api.flow.microsoft.com/test")
    response = httpx.Response(403, text="Forbidden", request=request)
    client = AsyncMock()
    client.list_connections.side_effect = httpx.HTTPStatusError(
        "forbidden", request=request, response=response,
    )

    result = await handle_connections(
        PaListConnectionsInput(environment_id="env-err"),
        client,
    )

    assert result["error"] == "http_error"
    assert result["tool"] == "pa_list_connections"
    assert result["status"] == 403
