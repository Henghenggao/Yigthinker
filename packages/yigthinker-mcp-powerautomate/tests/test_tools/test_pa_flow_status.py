"""Tests for pa_flow_status tool handler (Plan 12-05 RED/GREEN).

Happy path + empty runs list per D-23.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from yigthinker_mcp_powerautomate.tools.pa_flow_status import (
    PaFlowStatusInput,
    handle as handle_status,
)

pytestmark = pytest.mark.asyncio


async def test_happy_path_returns_run_summaries() -> None:
    """Returns mapped list of run summaries."""
    client = AsyncMock()
    client.list_flow_runs.return_value = [
        {
            "name": "run-001",
            "properties": {
                "status": "Succeeded",
                "startTime": "2026-04-10T10:00:00Z",
                "endTime": "2026-04-10T10:01:00Z",
            },
        },
        {
            "name": "run-002",
            "properties": {
                "status": "Failed",
                "startTime": "2026-04-10T11:00:00Z",
                "endTime": "2026-04-10T11:00:30Z",
            },
        },
    ]

    result = await handle_status(
        PaFlowStatusInput(
            flow_id="flow-abc",
            environment_id="env-001",
            top=5,
        ),
        client,
    )

    assert result["flow_id"] == "flow-abc"
    assert result["environment_id"] == "env-001"
    assert len(result["runs"]) == 2
    assert result["runs"][0]["run_id"] == "run-001"
    assert result["runs"][0]["status"] == "Succeeded"
    assert result["runs"][0]["start_time"] == "2026-04-10T10:00:00Z"
    assert result["runs"][1]["run_id"] == "run-002"
    assert result["runs"][1]["status"] == "Failed"
    client.list_flow_runs.assert_awaited_once_with("env-001", "flow-abc", 5)


async def test_empty_runs_list() -> None:
    """Empty runs list returns empty runs array."""
    client = AsyncMock()
    client.list_flow_runs.return_value = []

    result = await handle_status(
        PaFlowStatusInput(
            flow_id="flow-xyz",
            environment_id="env-002",
        ),
        client,
    )

    assert result["flow_id"] == "flow-xyz"
    assert result["runs"] == []


async def test_http_error_returns_error_dict() -> None:
    """HTTPStatusError is caught and returned as an is_error dict."""
    request = httpx.Request("GET", "https://api.flow.microsoft.com/test")
    response = httpx.Response(500, text="Internal server error", request=request)
    client = AsyncMock()
    client.list_flow_runs.side_effect = httpx.HTTPStatusError(
        "server error", request=request, response=response,
    )

    result = await handle_status(
        PaFlowStatusInput(
            flow_id="flow-err",
            environment_id="env-001",
        ),
        client,
    )

    assert result["error"] == "http_error"
    assert result["tool"] == "pa_flow_status"
    assert result["status"] == 500
