"""Tests for pa_pause_flow tool handler (Plan 12-05 RED/GREEN).

Disable calls stop_flow, enable calls start_flow, HTTP error per D-23.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from yigthinker_mcp_powerautomate.tools.pa_pause_flow import (
    PaPauseFlowInput,
    handle as handle_pause,
)

pytestmark = pytest.mark.asyncio


async def test_disable_calls_stop_flow() -> None:
    """action='disable' calls client.stop_flow."""
    client = AsyncMock()
    client.stop_flow.return_value = {"properties": {"state": "Stopped"}}

    result = await handle_pause(
        PaPauseFlowInput(
            flow_id="flow-abc",
            environment_id="env-001",
            action="disable",
        ),
        client,
    )

    assert result["flow_id"] == "flow-abc"
    assert result["environment_id"] == "env-001"
    assert result["action"] == "disable"
    assert result["result"] == "success"
    client.stop_flow.assert_awaited_once_with("env-001", "flow-abc")
    client.start_flow.assert_not_awaited()


async def test_enable_calls_start_flow() -> None:
    """action='enable' calls client.start_flow."""
    client = AsyncMock()
    client.start_flow.return_value = {"properties": {"state": "Started"}}

    result = await handle_pause(
        PaPauseFlowInput(
            flow_id="flow-xyz",
            environment_id="env-002",
            action="enable",
        ),
        client,
    )

    assert result["flow_id"] == "flow-xyz"
    assert result["environment_id"] == "env-002"
    assert result["action"] == "enable"
    assert result["result"] == "success"
    client.start_flow.assert_awaited_once_with("env-002", "flow-xyz")
    client.stop_flow.assert_not_awaited()


async def test_http_error_returns_error_dict() -> None:
    """HTTPStatusError is caught and returned as an is_error dict."""
    request = httpx.Request("POST", "https://api.flow.microsoft.com/test")
    response = httpx.Response(401, text="Unauthorized", request=request)
    client = AsyncMock()
    client.stop_flow.side_effect = httpx.HTTPStatusError(
        "unauthorized", request=request, response=response,
    )

    result = await handle_pause(
        PaPauseFlowInput(
            flow_id="flow-err",
            environment_id="env-001",
            action="disable",
        ),
        client,
    )

    assert result["error"] == "http_error"
    assert result["tool"] == "pa_pause_flow"
    assert result["status"] == 401
