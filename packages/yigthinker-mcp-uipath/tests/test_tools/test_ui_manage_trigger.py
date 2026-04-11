"""Tests for ui_manage_trigger tool handler (Plan 11-05 RED/GREEN)."""
from __future__ import annotations

import httpx
import pytest
import respx

from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient
from yigthinker_mcp_uipath.tools.ui_manage_trigger import (
    UiManageTriggerInput,
    handle as handle_manage,
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
async def test_happy_path_create_action_posts_schedule(
    mock_auth: UipathAuth,
) -> None:
    respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    # Release key lookup (create action resolves process_key -> release_key).
    respx.get(f"{BASE}/odata/Releases").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Key": "rel-key-1"}]}
        )
    )
    create_route = respx.post(f"{BASE}/odata/ProcessSchedules").mock(
        return_value=httpx.Response(
            201, json={"Id": 77, "Name": "morning", "Enabled": True}
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_manage(
            UiManageTriggerInput(
                process_key="test_flow",
                action="create",
                folder_path="Shared",
                cron="0 9 * * *",
                trigger_name="morning",
            ),
            client,
        )

    assert result["status"] == "created"
    assert result["schedule_id"] == 77
    assert result["process_key"] == "test_flow"
    assert result["action"] == "create"
    assert create_route.call_count == 1


@respx.mock
async def test_error_missing_cron_returns_dict(
    mock_auth: UipathAuth,
) -> None:
    # No HTTP routes mocked — handler MUST short-circuit before any HTTP.
    folders_route = respx.get(f"{BASE}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )

    async with OrchestratorClient(auth=mock_auth, base_url=BASE) as client:
        result = await handle_manage(
            UiManageTriggerInput(
                process_key="test_flow",
                action="create",
                folder_path="Shared",
                cron=None,
                trigger_name="morning",
            ),
            client,
        )

    assert result["error"] == "missing_cron"
    assert result["action"] == "create"
    # Cross-field validation MUST fire before resolving folder (no HTTP calls
    # at all — folders route untouched).
    assert folders_route.call_count == 0
