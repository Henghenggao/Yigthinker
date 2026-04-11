"""Tests for ui_deploy_process tool handler (Plan 11-05 RED/GREEN).

One happy path + one error path per D-23.
Fixtures comply with D-09 (UipathAuth 5-field signature, scope=STRING) and
D-13 (OrchestratorClient 2-arg constructor, no http= kwarg).
"""
from __future__ import annotations

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient
from yigthinker_mcp_uipath.tools.ui_deploy_process import (
    UiDeployProcessInput,
    handle as handle_deploy,
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
async def test_happy_path_deploys_workflow(
    tmp_path: object, mock_auth: UipathAuth
) -> None:
    script = tmp_path / "test_flow.py"  # type: ignore[attr-defined]
    script.write_text("print('hi')\nmain = lambda: 'ok'\n")

    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    upload_route = respx.post(
        f"{BASE}/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"Key": "test_flow:1.2.3", "ProcessVersion": "1.2.3"}
                ]
            },
        )
    )
    respx.post(f"{BASE}/odata/Releases").mock(
        return_value=httpx.Response(
            201,
            json={
                "Id": 99,
                "Key": "rel-key-99",
                "ProcessKey": "test_flow",
            },
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_deploy(
            UiDeployProcessInput(
                workflow_name="test_flow",
                script_path=str(script),
                folder_path="Shared",
                package_version="1.2.3",
            ),
            client,
        )

    assert result["status"] == "deployed"
    assert result["process_key"] == "test_flow"
    assert result["release_key"] == "rel-key-99"
    assert result["folder_path"] == "Shared"
    assert result["package_version"] == "1.2.3"
    # UploadPackage route was actually hit (sanity + multipart).
    assert upload_route.call_count == 1


@respx.mock
async def test_error_returns_dict_on_orchestrator_500(
    tmp_path: object, mock_auth: UipathAuth
) -> None:
    script = tmp_path / "test_flow.py"  # type: ignore[attr-defined]
    script.write_text("main = lambda: 'ok'\n")
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    respx.post(
        f"{BASE}/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    ).mock(return_value=httpx.Response(500, text="boom"))

    # Disable retry backoff sleeps so the test runs fast.
    import yigthinker_mcp_uipath.client as client_module

    async def _noop_sleep(*_a: object, **_kw: object) -> None:
        return None

    import asyncio as _asyncio

    original_sleep = _asyncio.sleep
    client_module.asyncio.sleep = _noop_sleep  # type: ignore[assignment]
    try:
        async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
            result = await handle_deploy(
                UiDeployProcessInput(
                    workflow_name="test_flow",
                    script_path=str(script),
                    folder_path="Shared",
                    package_version="1.0.0",
                ),
                client,
            )
    finally:
        client_module.asyncio.sleep = original_sleep  # type: ignore[assignment]

    assert result["error"] == "http_error"
    assert result["status"] == 500
    assert "detail" in result
