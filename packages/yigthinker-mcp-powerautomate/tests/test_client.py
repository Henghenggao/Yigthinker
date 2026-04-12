"""Unit tests for yigthinker_mcp_powerautomate.client.PowerAutomateClient (Plan 12-03).

Locks the following contracts before Plan 12-05 handlers build against them:
- D-16 constructor signature (auth, base_url) -- EXACTLY 2 args, no ``http`` kwarg.
- D-16 retry semantics: 3 attempts on 5xx / httpx.NetworkError, 4xx fails
  immediately, 30s timeout per request.
- D-18: ``api-version=2016-11-01`` appended to every request.
- Every endpoint uses ``/providers/Microsoft.ProcessSimple/environments/{env}/...``
  URL pattern per RESEARCH.md Finding 2.

Auth is mocked at the ``get_token`` level (D-26 separation of concerns) --
MSAL is never involved in these tests.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from tests.conftest import SAMPLE_BASE_URL
from yigthinker_mcp_powerautomate.auth import PowerAutomateAuth
from yigthinker_mcp_powerautomate.client import (
    API_VERSION,
    RETRY_BACKOFFS,
    REQUEST_TIMEOUT_S,
    PowerAutomateClient,
)

pytestmark = pytest.mark.asyncio

_PROVIDER = "/providers/Microsoft.ProcessSimple"
_ENV = "env-1"
_FLOW = "flow-123"
_BASE = f"{SAMPLE_BASE_URL}{_PROVIDER}/environments/{_ENV}"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_client(monkeypatch) -> PowerAutomateClient:
    """Create a PowerAutomateClient with auth.get_token mocked to return 'tok-test'."""
    auth = PowerAutomateAuth(
        tenant_id="test-tenant",
        client_id="test-client-id",
        client_secret="test-secret",
    )
    monkeypatch.setattr(
        PowerAutomateAuth,
        "get_token",
        staticmethod(lambda self=None: _fake_get_token()),
    )
    return PowerAutomateClient(auth=auth, base_url=SAMPLE_BASE_URL)


async def _fake_get_token(self=None) -> str:
    """Mock get_token that works as both bound and unbound method."""
    return "tok-test"


async def _noop_sleep(*_args, **_kwargs) -> None:
    """Drop-in replacement for asyncio.sleep so retry tests don't block."""
    return None


# ---------------------------------------------------------------------------
# 1. test_create_flow
# ---------------------------------------------------------------------------


@respx.mock
async def test_create_flow(monkeypatch):
    monkeypatch.setattr(
        PowerAutomateAuth, "get_token", _fake_get_token,
    )
    route = respx.post(f"{_BASE}/flows").mock(
        return_value=httpx.Response(
            200, json={"name": "new-flow-id", "properties": {"displayName": "Test"}}
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(
            tenant_id="t", client_id="c", client_secret="s",
        ),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.create_flow(
            env_id=_ENV,
            body={"properties": {"displayName": "Test"}},
        )
    finally:
        await client.aclose()
    assert result["name"] == "new-flow-id"
    # Assert Authorization header was sent with correct token.
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-test"
    # Assert api-version param.
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 2. test_get_flow
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_flow(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.get(f"{_BASE}/flows/{_FLOW}").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": _FLOW,
                "properties": {
                    "displayName": "My Flow",
                    "flowTriggerUri": "https://prod-00.westus.logic.azure.com/...",
                },
            },
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.get_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    assert result["name"] == _FLOW
    assert "flowTriggerUri" in result["properties"]
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 3. test_trigger_flow_run
# ---------------------------------------------------------------------------


@respx.mock
async def test_trigger_flow_run(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.post(f"{_BASE}/flows/{_FLOW}/triggers/manual/run").mock(
        return_value=httpx.Response(
            202, json={"statusCode": "Accepted", "headers": {"x-ms-workflow-run-id": "run-abc"}}
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.trigger_flow_run(
            env_id=_ENV,
            flow_id=_FLOW,
            trigger_input={"key": "value"},
        )
    finally:
        await client.aclose()
    assert result["statusCode"] == "Accepted"
    # Verify trigger_input was sent as request body.
    import json
    body = json.loads(route.calls.last.request.content)
    assert body == {"key": "value"}
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 4. test_list_flow_runs
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_flow_runs(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.get(f"{_BASE}/flows/{_FLOW}/runs").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"name": "run-1", "properties": {"status": "Succeeded"}},
                    {"name": "run-2", "properties": {"status": "Failed"}},
                ]
            },
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.list_flow_runs(env_id=_ENV, flow_id=_FLOW, top=5)
    finally:
        await client.aclose()
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "run-1"
    sent_url = str(route.calls.last.request.url)
    assert "$top=5" in sent_url or "%24top=5" in sent_url
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 5. test_stop_flow
# ---------------------------------------------------------------------------


@respx.mock
async def test_stop_flow(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.post(f"{_BASE}/flows/{_FLOW}/stop").mock(
        return_value=httpx.Response(200, json={})
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.stop_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    assert isinstance(result, dict)
    assert route.call_count == 1
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 6. test_start_flow
# ---------------------------------------------------------------------------


@respx.mock
async def test_start_flow(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.post(f"{_BASE}/flows/{_FLOW}/start").mock(
        return_value=httpx.Response(200, json={})
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.start_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    assert isinstance(result, dict)
    assert route.call_count == 1
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 7. test_list_connections
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_connections(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.get(
        f"{SAMPLE_BASE_URL}{_PROVIDER}/environments/{_ENV}/connections"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"name": "conn-1", "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_office365"}},
                    {"name": "conn-2", "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sql"}},
                ]
            },
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.list_connections(env_id=_ENV)
    finally:
        await client.aclose()
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "conn-1"
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 8. test_list_connections_filtered
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_connections_filtered(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.get(
        f"{SAMPLE_BASE_URL}{_PROVIDER}/environments/{_ENV}/connections"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"name": "conn-1", "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_office365"}},
                ]
            },
        )
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.list_connections(
            env_id=_ENV, connector_name="shared_office365",
        )
    finally:
        await client.aclose()
    assert len(result) == 1
    sent_url = str(route.calls.last.request.url)
    assert "$filter" in sent_url or "%24filter" in sent_url
    assert "shared_office365" in sent_url
    assert f"api-version={API_VERSION}" in sent_url


# ---------------------------------------------------------------------------
# 9. test_retry_on_5xx
# ---------------------------------------------------------------------------


@respx.mock
async def test_retry_on_5xx(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    monkeypatch.setattr(
        "yigthinker_mcp_powerautomate.client.asyncio.sleep", _noop_sleep,
    )
    route = respx.get(f"{_BASE}/flows/{_FLOW}").mock(
        side_effect=[
            httpx.Response(500, text="Internal error"),
            httpx.Response(503, text="Try later"),
            httpx.Response(
                200,
                json={"name": _FLOW, "properties": {"displayName": "OK"}},
            ),
        ]
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        result = await client.get_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    assert result["name"] == _FLOW
    assert route.call_count == 3


# ---------------------------------------------------------------------------
# 10. test_no_retry_on_4xx
# ---------------------------------------------------------------------------


@respx.mock
async def test_no_retry_on_4xx(monkeypatch):
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    monkeypatch.setattr(
        "yigthinker_mcp_powerautomate.client.asyncio.sleep", _noop_sleep,
    )
    route = respx.get(f"{_BASE}/flows/{_FLOW}").mock(
        return_value=httpx.Response(404, text="Not found")
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# 11. test_api_version_appended_to_every_request
# ---------------------------------------------------------------------------


@respx.mock
async def test_api_version_appended_to_every_request(monkeypatch):
    """Verify that api-version=2016-11-01 is present on requests regardless of endpoint."""
    monkeypatch.setattr(PowerAutomateAuth, "get_token", _fake_get_token)
    route = respx.post(f"{_BASE}/flows/{_FLOW}/start").mock(
        return_value=httpx.Response(200, json={})
    )
    client = PowerAutomateClient(
        auth=PowerAutomateAuth(tenant_id="t", client_id="c", client_secret="s"),
        base_url=SAMPLE_BASE_URL,
    )
    try:
        await client.start_flow(env_id=_ENV, flow_id=_FLOW)
    finally:
        await client.aclose()
    sent_url = str(route.calls.last.request.url)
    assert f"api-version={API_VERSION}" in sent_url
    assert API_VERSION == "2016-11-01"


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


def test_retry_backoffs_are_1_2_4():
    assert RETRY_BACKOFFS == (1.0, 2.0, 4.0)


def test_request_timeout_is_30s():
    assert REQUEST_TIMEOUT_S == 30.0


def test_api_version_constant():
    assert API_VERSION == "2016-11-01"
