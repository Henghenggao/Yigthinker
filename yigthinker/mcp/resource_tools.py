from __future__ import annotations

import json

from pydantic import BaseModel

from yigthinker.mcp.client import MCPClient
from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class MCPListResourcesInput(BaseModel):
    server: str | None = None


class MCPListResourcesTool:
    name = "mcp_list_resources"
    description = "List available MCP resources across connected servers. Optionally filter by server name."
    input_schema = MCPListResourcesInput

    def __init__(self, resource_clients: dict[str, MCPClient]) -> None:
        self._clients = resource_clients

    async def execute(self, input: MCPListResourcesInput, ctx: SessionContext) -> ToolResult:
        try:
            all_resources: list[dict[str, str]] = []
            for server_name, client in self._clients.items():
                if input.server is not None and server_name != input.server:
                    continue
                resources = await client.list_resources()
                for r in resources:
                    r["server"] = server_name
                    all_resources.append(r)
            return ToolResult(tool_use_id="", content=json.dumps(all_resources, ensure_ascii=False))
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


class MCPReadResourceInput(BaseModel):
    uri: str


class MCPReadResourceTool:
    name = "mcp_read_resource"
    description = "Read the contents of an MCP resource by URI. Use mcp_list_resources first to discover available URIs."
    input_schema = MCPReadResourceInput

    def __init__(self, resource_clients: dict[str, MCPClient]) -> None:
        self._clients = resource_clients
        self._uri_to_server: dict[str, str] = {}

    async def _resolve_server(self, uri: str) -> str | None:
        """Find which server owns a URI. Uses cache, refreshes on miss."""
        if uri in self._uri_to_server:
            return self._uri_to_server[uri]

        # Refresh cache
        for server_name, client in self._clients.items():
            resources = await client.list_resources()
            for r in resources:
                self._uri_to_server[r["uri"]] = server_name

        return self._uri_to_server.get(uri)

    async def execute(self, input: MCPReadResourceInput, ctx: SessionContext) -> ToolResult:
        try:
            server_name = await self._resolve_server(input.uri)
            if server_name is None:
                return ToolResult(
                    tool_use_id="",
                    content=f"Resource URI not found: {input.uri}. Use mcp_list_resources to see available resources.",
                    is_error=True,
                )
            client = self._clients[server_name]
            content = await client.read_resource(input.uri)
            return ToolResult(tool_use_id="", content=content)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
