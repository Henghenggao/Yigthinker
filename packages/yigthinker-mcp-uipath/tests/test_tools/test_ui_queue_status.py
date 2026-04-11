"""Tests for ui_queue_status tool handler (Plan 11-05 RED/GREEN).

MEDIUM 2 guard: mocks the CORRECT OData endpoint
    /odata/QueueItems/UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount(queueDefinitionId=<id>,daysNo=<n>)
NOT the legacy /odata/Queues/.../GetQueueItemsCounts typo.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient
from yigthinker_mcp_uipath.tools.ui_queue_status import (
    UiQueueStatusInput,
    handle as handle_queue,
)

pytestmark = pytest.mark.asyncio

BASE = "https://cloud.uipath.com/acmecorp/DefaultTenant/orchestrator_"

COUNTS_URL = (
    f"{BASE}/odata/QueueItems/"
    f"UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount"
    f"(queueDefinitionId=7,daysNo=7)"
)


@pytest.fixture
def mock_auth(monkeypatch: pytest.MonkeyPatch) -> UipathAuth:
    auth = UipathAuth(
        client_id="test_client",
        client_secret="test_secret",
        tenant_name="DefaultTenant",
        organization="acmecorp",
        scope="OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring",
    )

    async def fake_headers(self: UipathAuth, http: httpx.AsyncClient) -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    monkeypatch.setattr(UipathAuth, "auth_headers", fake_headers)
    return auth


@respx.mock
async def test_happy_path_returns_queue_counts(mock_auth: UipathAuth) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    respx.get(f"{BASE}/odata/QueueDefinitions").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 7, "Name": "Invoices"}]}
        )
    )
    counts_route = respx.get(COUNTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "New": 5,
                "InProgress": 2,
                "Failed": 1,
                "Successful": 42,
            },
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_queue(
            UiQueueStatusInput(queue_name="Invoices", folder_path="Shared"),
            client,
        )

    assert result["queue_name"] == "Invoices"
    assert result["new"] == 5
    assert result["in_progress"] == 2
    assert result["failed"] == 1
    assert result["successful"] == 42
    assert counts_route.call_count == 1


@respx.mock
async def test_error_queue_not_found_returns_dict(
    mock_auth: UipathAuth,
) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    respx.get(f"{BASE}/odata/QueueDefinitions").mock(
        return_value=httpx.Response(200, json={"value": []})
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_queue(
            UiQueueStatusInput(queue_name="Invoices", folder_path="Shared"),
            client,
        )

    assert result["error"] == "queue_not_found"
    assert result["queue_name"] == "Invoices"
