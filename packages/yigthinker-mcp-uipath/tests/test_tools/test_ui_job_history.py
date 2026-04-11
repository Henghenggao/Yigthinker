"""Tests for ui_job_history tool handler (Plan 11-05 RED/GREEN)."""
from __future__ import annotations

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient
from yigthinker_mcp_uipath.tools.ui_job_history import (
    UiJobHistoryInput,
    handle as handle_history,
)

pytestmark = pytest.mark.asyncio

BASE = "https://cloud.uipath.com/acmecorp/DefaultTenant/orchestrator_"


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
async def test_happy_path_lists_recent_jobs(mock_auth: UipathAuth) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    # Release-key lookup (handler resolves process_key -> release_key before
    # listing jobs, because client.list_jobs filters on Release/Key).
    respx.get(f"{BASE}/odata/Releases").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Key": "rel-key-1"}]}
        )
    )
    respx.get(f"{BASE}/odata/Jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "Id": 1,
                        "State": "Successful",
                        "StartTime": "2026-04-01T10:00:00Z",
                        "EndTime": "2026-04-01T10:05:00Z",
                        "Info": "ok",
                    },
                    {
                        "Id": 2,
                        "State": "Faulted",
                        "StartTime": "2026-04-02T10:00:00Z",
                        "EndTime": "2026-04-02T10:03:00Z",
                        "Info": "err",
                    },
                ]
            },
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_history(
            UiJobHistoryInput(
                process_key="test_flow", folder_path="Shared", top=10
            ),
            client,
        )

    assert result["process_key"] == "test_flow"
    assert result["count"] == 2
    assert len(result["jobs"]) == 2
    assert result["jobs"][0]["id"] == 1
    assert result["jobs"][0]["state"] == "Successful"
    assert result["jobs"][1]["state"] == "Faulted"


@respx.mock
async def test_error_on_4xx_returns_dict(mock_auth: UipathAuth) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    respx.get(f"{BASE}/odata/Releases").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Key": "rel-key-1"}]}
        )
    )
    respx.get(f"{BASE}/odata/Jobs").mock(
        return_value=httpx.Response(400, text="bad request")
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_history(
            UiJobHistoryInput(
                process_key="test_flow", folder_path="Shared", top=10
            ),
            client,
        )

    assert result["error"] == "http_error"
    assert result["status"] == 400
