"""Smoke test: spawn MCP stdio server as a subprocess and verify ``list_tools``.

This is the integration guard that the low-level :class:`Server` + stdio
transport wiring actually works end-to-end. It does NOT call any tool
handler -- those are covered in-process by ``tests/test_tools/*`` with
``respx`` mocks. This test proves:

- ``python -m yigthinker_mcp_powerautomate`` boots without network (handlers
  are lazy) given the 3 required env vars plus the default-fallback path for
  the 3 optional vars (SCOPE, BASE_URL, AUTHORITY).
- The server responds to ``list_tools`` with exactly the 5 expected Power
  Automate tools per CONTEXT.md D-23.
- Each advertised tool carries a non-empty description and an object-typed
  ``inputSchema`` with properties (the shape core Yigthinker's
  ``_MCPToolWrapper`` flattens into a Pydantic model).
"""
from __future__ import annotations

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.asyncio

EXPECTED_TOOLS = {
    "pa_deploy_flow",
    "pa_trigger_flow",
    "pa_flow_status",
    "pa_pause_flow",
    "pa_list_connections",
}


async def test_server_smoke_list_tools_returns_5() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "yigthinker_mcp_powerautomate"],
        env={
            **os.environ,
            "POWERAUTOMATE_TENANT_ID": "smoke-tenant",
            "POWERAUTOMATE_CLIENT_ID": "smoke-id",
            "POWERAUTOMATE_CLIENT_SECRET": "smoke-secret",
            # POWERAUTOMATE_SCOPE intentionally omitted -- verifies default fallback
            # POWERAUTOMATE_BASE_URL intentionally omitted -- verifies default fallback
            # POWERAUTOMATE_AUTHORITY intentionally omitted -- verifies default fallback
            "PYTHONUNBUFFERED": "1",
        },
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()

    names = {tool.name for tool in tools_result.tools}
    assert names == EXPECTED_TOOLS, (
        f"Missing or extra tools: {names.symmetric_difference(EXPECTED_TOOLS)}"
    )
    assert len(tools_result.tools) == 5

    for tool in tools_result.tools:
        assert tool.description, f"Tool {tool.name} has empty description"
        schema = tool.inputSchema
        assert isinstance(schema, dict), f"Tool {tool.name} inputSchema is not a dict"
        assert schema.get("type") == "object", (
            f"Tool {tool.name} inputSchema not object type"
        )
        assert "properties" in schema, (
            f"Tool {tool.name} inputSchema missing properties"
        )
