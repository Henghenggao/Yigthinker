"""Unit tests for yigthinker_mcp_uipath.client.OrchestratorClient (Plan 11-03).

Locks the following contracts before Plan 11-05 handlers build against them:
- D-13 constructor signature (auth, base_url) — EXACTLY 2 args, no ``http`` kwarg.
- D-12/D-13 retry semantics: 3 attempts on 5xx / httpx.NetworkError, 4xx fails
  immediately, 30s timeout per request.
- Pitfall 2 (folder header): every folder-scoped request injects
  ``X-UIPATH-OrganizationUnitId: <folder_id>``.
- Finding 3 (InputArguments as JSON string): ``start_job`` must serialize
  ``input_arguments`` into a JSON STRING under ``startInfo.InputArguments`` —
  never an object — or UiPath rejects the StartJobs call.
- RESEARCH.md Finding 3 queue OData path:
  ``/odata/QueueItems/UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount(queueDefinitionId=<id>,daysNo=<n>)``
  (NOT the legacy ``/odata/Queues/UiPathODataSvc.GetQueueItemsCounts`` form).
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.conftest import SAMPLE_BASE_URL, SAMPLE_TOKEN_URL
from yigthinker_mcp_uipath.auth import UipathAuth
from yigthinker_mcp_uipath.client import OrchestratorClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_client() -> OrchestratorClient:
    auth = UipathAuth(
        client_id="id",
        client_secret="secret",
        tenant_name="DefaultTenant",
        organization="acmecorp",
        scope="OR.Execution OR.Jobs OR.Folders.Read",
    )
    # D-13 LOCKED: exactly 2 args — auth + base_url. The httpx.AsyncClient
    # is created internally. NO ``http`` kwarg allowed.
    return OrchestratorClient(auth=auth, base_url=SAMPLE_BASE_URL)


def _mock_token() -> respx.Route:
    return respx.post(SAMPLE_TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok", "expires_in": 3600}
        )
    )


async def _noop_sleep(*_args, **_kwargs) -> None:
    """Drop-in replacement for asyncio.sleep so retry tests don't block."""
    return None


# ---------------------------------------------------------------------------
# Folder resolution
# ---------------------------------------------------------------------------


@respx.mock
async def test_resolve_folder_id_calls_filter_and_returns_int():
    _mock_token()
    respx.get(f"{SAMPLE_BASE_URL}/odata/Folders").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
        )
    )
    client = _make_client()
    try:
        folder_id = await client.resolve_folder_id("Shared")
    finally:
        await client.aclose()
    assert folder_id == 42


@respx.mock
async def test_resolve_folder_id_raises_on_empty():
    _mock_token()
    respx.get(f"{SAMPLE_BASE_URL}/odata/Folders").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    client = _make_client()
    try:
        with pytest.raises(ValueError, match="folder not found"):
            await client.resolve_folder_id("NonExistent")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# ui_deploy_process: upload_package + create_release
# ---------------------------------------------------------------------------


@respx.mock
async def test_upload_package_sends_folder_header_and_returns_process_key():
    _mock_token()
    upload_url = (
        f"{SAMPLE_BASE_URL}/odata/Processes/"
        f"UiPath.Server.Configuration.OData.UploadPackage"
    )
    upload_route = respx.post(upload_url).mock(
        return_value=httpx.Response(
            200, json={"value": [{"Key": "pk_abc", "ProcessVersion": "1.0.0"}]}
        )
    )
    client = _make_client()
    try:
        result = await client.upload_package(
            folder_id=42,
            package_bytes=b"PK\x03\x04dummynupkgbytes",
            package_filename="test.nupkg",
        )
    finally:
        await client.aclose()
    assert result["Key"] == "pk_abc"
    assert result["ProcessVersion"] == "1.0.0"
    assert (
        upload_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


@respx.mock
async def test_create_release_posts_release_body():
    _mock_token()
    create_route = respx.post(f"{SAMPLE_BASE_URL}/odata/Releases").mock(
        return_value=httpx.Response(
            201, json={"Id": 123, "Key": "rk_def", "ProcessKey": "monthly_recon"}
        )
    )
    client = _make_client()
    try:
        result = await client.create_release(
            folder_id=42, workflow_name="monthly_recon", version="1.0.0"
        )
    finally:
        await client.aclose()
    assert result["Key"] == "rk_def"
    body = json.loads(create_route.calls.last.request.content)
    assert body["ProcessKey"] == "monthly_recon"
    assert body["ProcessVersion"] == "1.0.0"
    assert (
        create_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


# ---------------------------------------------------------------------------
# ui_trigger_job: release key lookup + start_job
# ---------------------------------------------------------------------------


@respx.mock
async def test_start_job_serializes_input_arguments_as_json_string():
    _mock_token()
    start_url = f"{SAMPLE_BASE_URL}/odata/Jobs/UiPath.Server.Jobs.StartJobs"
    start_route = respx.post(start_url).mock(
        return_value=httpx.Response(
            200, json={"value": [{"Key": "jk_001", "State": "Pending"}]}
        )
    )
    client = _make_client()
    try:
        await client.start_job(
            folder_id=42,
            release_key="rk_def",
            input_arguments={"key": "value"},
        )
    finally:
        await client.aclose()
    body = json.loads(start_route.calls.last.request.content)
    # CRITICAL Finding 3: InputArguments is a JSON STRING, not a dict.
    assert isinstance(body["startInfo"]["InputArguments"], str)
    assert json.loads(body["startInfo"]["InputArguments"]) == {"key": "value"}
    assert body["startInfo"]["ReleaseKey"] == "rk_def"
    assert body["startInfo"]["Strategy"] == "ModernJobsCount"
    assert body["startInfo"]["JobsCount"] == 1
    assert (
        start_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


# ---------------------------------------------------------------------------
# ui_job_history
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_jobs_filters_by_release_key():
    _mock_token()
    list_route = respx.get(f"{SAMPLE_BASE_URL}/odata/Jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"Id": 1, "Key": "jk_1", "State": "Successful"},
                    {"Id": 2, "Key": "jk_2", "State": "Faulted"},
                ]
            },
        )
    )
    client = _make_client()
    try:
        jobs = await client.list_jobs(
            folder_id=42, release_key="rk_def", top=10
        )
    finally:
        await client.aclose()
    assert isinstance(jobs, list)
    assert len(jobs) == 2
    assert jobs[0]["Key"] == "jk_1"
    # Verify $filter param was sent.
    sent_url = str(list_route.calls.last.request.url)
    assert "Release/Key" in sent_url or "Release%2FKey" in sent_url
    assert "rk_def" in sent_url
    assert (
        list_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


# ---------------------------------------------------------------------------
# ui_manage_trigger: create/update/delete schedules
# ---------------------------------------------------------------------------


@respx.mock
async def test_create_schedule_posts_release_key_and_cron():
    _mock_token()
    create_route = respx.post(f"{SAMPLE_BASE_URL}/odata/ProcessSchedules").mock(
        return_value=httpx.Response(
            201, json={"Id": 7, "Name": "nightly", "Enabled": True}
        )
    )
    client = _make_client()
    try:
        result = await client.create_schedule(
            folder_id=42,
            name="nightly",
            release_key="rk_def",
            cron="0 2 * * *",
        )
    finally:
        await client.aclose()
    assert result["Id"] == 7
    body = json.loads(create_route.calls.last.request.content)
    assert body["Name"] == "nightly"
    assert body["ReleaseKey"] == "rk_def"
    assert body["StartProcessCron"] == "0 2 * * *"
    assert body["Enabled"] is True
    assert body["TimeZoneId"] == "UTC"
    assert (
        create_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


@respx.mock
async def test_update_schedule_patches_enabled_flag():
    _mock_token()
    patch_route = respx.patch(
        f"{SAMPLE_BASE_URL}/odata/ProcessSchedules(123)"
    ).mock(
        return_value=httpx.Response(
            200, json={"Id": 123, "Enabled": False}
        )
    )
    client = _make_client()
    try:
        result = await client.update_schedule(
            folder_id=42, schedule_id=123, enabled=False
        )
    finally:
        await client.aclose()
    body = json.loads(patch_route.calls.last.request.content)
    assert body == {"Enabled": False}
    assert result["Enabled"] is False
    assert (
        patch_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


@respx.mock
async def test_delete_schedule_returns_none():
    _mock_token()
    del_route = respx.delete(
        f"{SAMPLE_BASE_URL}/odata/ProcessSchedules(123)"
    ).mock(return_value=httpx.Response(204))
    client = _make_client()
    try:
        result = await client.delete_schedule(folder_id=42, schedule_id=123)
    finally:
        await client.aclose()
    assert result is None
    assert del_route.call_count == 1
    assert (
        del_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


# ---------------------------------------------------------------------------
# ui_queue_status
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_queue_id_filters_by_name():
    _mock_token()
    qdef_route = respx.get(f"{SAMPLE_BASE_URL}/odata/QueueDefinitions").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 99, "Name": "critical_q"}]}
        )
    )
    client = _make_client()
    try:
        queue_id = await client.get_queue_id(
            folder_id=42, queue_name="critical_q"
        )
    finally:
        await client.aclose()
    assert queue_id == 99
    sent_url = str(qdef_route.calls.last.request.url)
    assert "critical_q" in sent_url
    assert (
        qdef_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


@respx.mock
async def test_get_queue_status_count_returns_dict():
    _mock_token()
    # Correct OData path per Finding 3 — NOT the legacy
    # /odata/Queues/UiPathODataSvc.GetQueueItemsCounts form.
    status_url = (
        f"{SAMPLE_BASE_URL}/odata/QueueItems/"
        f"UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount"
        f"(queueDefinitionId=7,daysNo=7)"
    )
    status_route = respx.get(status_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "New": 5,
                "InProgress": 2,
                "Successful": 10,
                "Failed": 1,
            },
        )
    )
    client = _make_client()
    try:
        counts = await client.get_queue_status_count(
            folder_id=42, queue_id=7, days_no=7
        )
    finally:
        await client.aclose()
    assert counts["New"] == 5
    assert counts["Failed"] == 1
    assert status_route.call_count == 1
    assert (
        status_route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"]
        == "42"
    )


# ---------------------------------------------------------------------------
# Retry semantics (D-13): 3 attempts on 5xx / NetworkError, 4xx immediate fail.
# ---------------------------------------------------------------------------


@respx.mock
async def test_retry_on_5xx_then_succeed(monkeypatch):
    _mock_token()
    monkeypatch.setattr(
        "yigthinker_mcp_uipath.client.asyncio.sleep", _noop_sleep
    )
    upload_url = (
        f"{SAMPLE_BASE_URL}/odata/Processes/"
        f"UiPath.Server.Configuration.OData.UploadPackage"
    )
    route = respx.post(upload_url).mock(
        side_effect=[
            httpx.Response(500, text="Internal error"),
            httpx.Response(503, text="Try later"),
            httpx.Response(
                200,
                json={"value": [{"Key": "pk_xyz", "ProcessVersion": "1.0"}]},
            ),
        ]
    )
    client = _make_client()
    try:
        result = await client.upload_package(
            folder_id=42,
            package_bytes=b"data",
            package_filename="t.nupkg",
        )
    finally:
        await client.aclose()
    assert result["Key"] == "pk_xyz"
    assert route.call_count == 3


@respx.mock
async def test_retry_on_network_error_then_succeed(monkeypatch):
    _mock_token()
    monkeypatch.setattr(
        "yigthinker_mcp_uipath.client.asyncio.sleep", _noop_sleep
    )
    folders_url = f"{SAMPLE_BASE_URL}/odata/Folders"
    route = respx.get(folders_url).mock(
        side_effect=[
            httpx.NetworkError("conn refused"),
            httpx.NetworkError("conn reset"),
            httpx.Response(
                200,
                json={"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]},
            ),
        ]
    )
    client = _make_client()
    try:
        folder_id = await client.resolve_folder_id("Shared")
    finally:
        await client.aclose()
    assert folder_id == 42
    assert route.call_count == 3


@respx.mock
async def test_no_retry_on_4xx(monkeypatch):
    _mock_token()
    monkeypatch.setattr(
        "yigthinker_mcp_uipath.client.asyncio.sleep", _noop_sleep
    )
    upload_url = (
        f"{SAMPLE_BASE_URL}/odata/Processes/"
        f"UiPath.Server.Configuration.OData.UploadPackage"
    )
    route = respx.post(upload_url).mock(
        return_value=httpx.Response(404, text="Not found")
    )
    client = _make_client()
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.upload_package(
                folder_id=42,
                package_bytes=b"data",
                package_filename="t.nupkg",
            )
    finally:
        await client.aclose()
    assert route.call_count == 1


@respx.mock
async def test_5xx_after_max_retries_raises(monkeypatch):
    _mock_token()
    monkeypatch.setattr(
        "yigthinker_mcp_uipath.client.asyncio.sleep", _noop_sleep
    )
    upload_url = (
        f"{SAMPLE_BASE_URL}/odata/Processes/"
        f"UiPath.Server.Configuration.OData.UploadPackage"
    )
    route = respx.post(upload_url).mock(
        return_value=httpx.Response(500, text="Internal error")
    )
    client = _make_client()
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.upload_package(
                folder_id=42,
                package_bytes=b"data",
                package_filename="t.nupkg",
            )
    finally:
        await client.aclose()
    assert route.call_count == 3


# ---------------------------------------------------------------------------
# Release key lookup (Plan 11-05 ui_trigger_job dep)
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_release_key_by_process_returns_key():
    _mock_token()
    route = respx.get(f"{SAMPLE_BASE_URL}/odata/Releases").mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"Key": "rk-abc-123", "ProcessKey": "test_flow"}]},
        )
    )
    client = _make_client()
    try:
        release_key = await client.get_release_key_by_process(42, "test_flow")
    finally:
        await client.aclose()
    assert release_key == "rk-abc-123"
    # Folder header must be set on this lookup (folder-scoped endpoint).
    assert (
        route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"] == "42"
    )
    sent_url = str(route.calls.last.request.url)
    assert "ProcessKey" in sent_url
    assert "test_flow" in sent_url


@respx.mock
async def test_get_release_key_by_process_raises_on_empty():
    _mock_token()
    respx.get(f"{SAMPLE_BASE_URL}/odata/Releases").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    client = _make_client()
    try:
        with pytest.raises(LookupError, match="No release found"):
            await client.get_release_key_by_process(42, "ghost_flow")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Schedule id lookup (Plan 11-05 ui_manage_trigger dep)
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_schedule_id_by_name_returns_id():
    _mock_token()
    route = respx.get(f"{SAMPLE_BASE_URL}/odata/ProcessSchedules").mock(
        return_value=httpx.Response(
            200, json={"value": [{"Id": 77, "Name": "nightly"}]}
        )
    )
    client = _make_client()
    try:
        sched_id = await client.get_schedule_id_by_name(42, "nightly")
    finally:
        await client.aclose()
    assert sched_id == 77
    assert (
        route.calls.last.request.headers["X-UIPATH-OrganizationUnitId"] == "42"
    )
    sent_url = str(route.calls.last.request.url)
    assert "Name" in sent_url
    assert "nightly" in sent_url


@respx.mock
async def test_get_schedule_id_by_name_raises_on_empty():
    _mock_token()
    respx.get(f"{SAMPLE_BASE_URL}/odata/ProcessSchedules").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    client = _make_client()
    try:
        with pytest.raises(LookupError, match="No schedule found"):
            await client.get_schedule_id_by_name(42, "ghost_trigger")
    finally:
        await client.aclose()
