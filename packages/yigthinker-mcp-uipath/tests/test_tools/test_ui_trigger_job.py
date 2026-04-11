"""Tests for ui_trigger_job tool handler (Plan 11-05 RED/GREEN).

D-09 + D-13 fixture shape. Finding 3 guard: InputArguments MUST be a JSON
string (not a dict) inside startInfo — the client's start_job handles the
json.dumps() internally; the handler just passes the dict through.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient
from yigthinker_mcp_uipath.tools.ui_trigger_job import (
    UiTriggerJobInput,
    handle as handle_trigger,
)

pytestmark = pytest.mark.asyncio

BASE = "https://cloud.uipath.com/acmecorp/DefaultTenant/orchestrator_"

# Client path — matches yigthinker_mcp_uipath.client.start_job (NOT the
# OData.StartJobs path in the plan draft, which is incorrect for modern
# Orchestrator).
START_JOBS_URL = f"{BASE}/odata/Jobs/UiPath.Server.Jobs.StartJobs"


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
async def test_happy_path_starts_job_with_json_string_args(
    mock_auth: UipathAuth,
) -> None:
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
    start_route = respx.post(START_JOBS_URL).mock(
        return_value=httpx.Response(
            201, json={"value": [{"Id": 555, "State": "Running"}]}
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_trigger(
            UiTriggerJobInput(
                process_key="test_flow",
                folder_path="Shared",
                input_arguments={"foo": "bar", "count": 3},
            ),
            client,
        )

    # Pitfall: InputArguments must be JSON STRING not dict (Finding 3).
    body = json.loads(start_route.calls.last.request.content)
    assert isinstance(body["startInfo"]["InputArguments"], str)
    assert json.loads(body["startInfo"]["InputArguments"]) == {
        "foo": "bar",
        "count": 3,
    }
    assert result["state"] == "Running"
    assert result["job_id"] == 555
    assert result["process_key"] == "test_flow"


@respx.mock
async def test_error_returns_dict_on_folder_not_found(
    mock_auth: UipathAuth,
) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(200, json={"value": []})
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_trigger(
            UiTriggerJobInput(process_key="test_flow", folder_path="Shared"),
            client,
        )

    assert result["error"] == "folder_not_found"
    assert result["folder_path"] == "Shared"
