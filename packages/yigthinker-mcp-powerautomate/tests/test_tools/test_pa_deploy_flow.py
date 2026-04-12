"""Tests for pa_deploy_flow tool handler (Plan 12-05 RED/GREEN).

Happy path + fallback trigger URL + error path per D-19/D-22.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from yigthinker_mcp_powerautomate.tools.pa_deploy_flow import (
    PaDeployFlowInput,
    handle as handle_deploy,
)

pytestmark = pytest.mark.asyncio


async def test_happy_path_deploys_flow_with_trigger_url() -> None:
    """Create flow returns flowTriggerUri directly."""
    client = AsyncMock()
    client.create_flow.return_value = {
        "name": "flow-abc-123",
        "properties": {
            "flowTriggerUri": "https://prod.logic.azure.com/callback/1234",
        },
    }

    result = await handle_deploy(
        PaDeployFlowInput(
            flow_name="test-notify",
            environment_id="env-001",
            recipients=["a@example.com"],
        ),
        client,
    )

    assert result["flow_id"] == "flow-abc-123"
    assert result["http_trigger_url"] == "https://prod.logic.azure.com/callback/1234"
    assert result["flow_name"] == "test-notify"
    assert result["environment_id"] == "env-001"
    client.create_flow.assert_awaited_once()
    # get_flow should NOT be called when create_flow already has the URI.
    client.get_flow.assert_not_awaited()


async def test_fallback_gets_trigger_url_from_get_flow() -> None:
    """When create_flow response lacks flowTriggerUri, fall back to get_flow."""
    client = AsyncMock()
    client.create_flow.return_value = {
        "name": "flow-xyz-789",
        "properties": {},
    }
    client.get_flow.return_value = {
        "properties": {
            "flowTriggerUri": "https://prod.logic.azure.com/callback/9999",
        },
    }

    result = await handle_deploy(
        PaDeployFlowInput(
            flow_name="fallback-flow",
            environment_id="env-002",
            recipients=["b@example.com", "c@example.com"],
            subject_template="Alert: {workflow_name}",
            display_name="My Fallback",
        ),
        client,
    )

    assert result["flow_id"] == "flow-xyz-789"
    assert result["http_trigger_url"] == "https://prod.logic.azure.com/callback/9999"
    assert result["flow_name"] == "fallback-flow"
    client.get_flow.assert_awaited_once_with("env-002", "flow-xyz-789")


async def test_http_error_returns_error_dict() -> None:
    """HTTPStatusError is caught and returned as an is_error dict."""
    request = httpx.Request("POST", "https://api.flow.microsoft.com/test")
    response = httpx.Response(403, text="Forbidden", request=request)
    client = AsyncMock()
    client.create_flow.side_effect = httpx.HTTPStatusError(
        "forbidden", request=request, response=response,
    )

    result = await handle_deploy(
        PaDeployFlowInput(
            flow_name="bad-flow",
            environment_id="env-003",
            recipients=["x@example.com"],
        ),
        client,
    )

    assert result["error"] == "http_error"
    assert result["tool"] == "pa_deploy_flow"
    assert result["status"] == 403
    assert "Forbidden" in result["detail"]
