"""Tests for pa_trigger_flow tool handler (Plan 12-05 RED/GREEN).

Happy path + empty trigger_input + HTTP error per D-23.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from yigthinker_mcp_powerautomate.tools.pa_trigger_flow import (
    PaTriggerFlowInput,
    handle as handle_trigger,
)

pytestmark = pytest.mark.asyncio


async def test_happy_path_triggers_flow() -> None:
    """Trigger with payload returns run status + run_id."""
    client = AsyncMock()
    client.trigger_flow_run.return_value = {
        "name": "run-001",
        "properties": {"status": "Running"},
    }

    result = await handle_trigger(
        PaTriggerFlowInput(
            flow_id="flow-abc",
            environment_id="env-001",
            trigger_input={"message": "hello"},
        ),
        client,
    )

    assert result["flow_id"] == "flow-abc"
    assert result["run_id"] == "run-001"
    assert result["status"] == "Running"
    assert result["environment_id"] == "env-001"
    client.trigger_flow_run.assert_awaited_once_with(
        "env-001", "flow-abc", {"message": "hello"},
    )


async def test_empty_trigger_input() -> None:
    """Empty trigger_input defaults to empty dict."""
    client = AsyncMock()
    client.trigger_flow_run.return_value = {
        "name": "run-002",
        "properties": {"status": "Succeeded"},
    }

    result = await handle_trigger(
        PaTriggerFlowInput(
            flow_id="flow-xyz",
            environment_id="env-002",
        ),
        client,
    )

    assert result["run_id"] == "run-002"
    assert result["status"] == "Succeeded"
    client.trigger_flow_run.assert_awaited_once_with("env-002", "flow-xyz", {})


async def test_http_error_returns_error_dict() -> None:
    """HTTPStatusError is caught and returned as an is_error dict."""
    request = httpx.Request("POST", "https://api.flow.microsoft.com/test")
    response = httpx.Response(404, text="Flow not found", request=request)
    client = AsyncMock()
    client.trigger_flow_run.side_effect = httpx.HTTPStatusError(
        "not found", request=request, response=response,
    )

    result = await handle_trigger(
        PaTriggerFlowInput(
            flow_id="flow-missing",
            environment_id="env-001",
            trigger_input={},
        ),
        client,
    )

    assert result["error"] == "http_error"
    assert result["tool"] == "pa_trigger_flow"
    assert result["status"] == 404
