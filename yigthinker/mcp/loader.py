from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, create_model

from yigthinker.mcp.client import MCPClient, MCPToolDef
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import ToolResult


def _build_pydantic_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}
    for field_name, field_schema in props.items():
        field_type: type = str
        json_type = field_schema.get("type", "string")
        if json_type == "integer":
            field_type = int
        elif json_type == "number":
            field_type = float
        elif json_type == "boolean":
            field_type = bool
        elif json_type == "array":
            field_type = list

        if field_name in required:
            fields[field_name] = (field_type, ...)
        else:
            fields[field_name] = (field_type | None, field_schema.get("default"))

    return create_model(name, **fields)  # type: ignore[call-overload]


class _MCPToolWrapper:
    def __init__(self, tool_def: MCPToolDef, client: MCPClient) -> None:
        self.name = tool_def.name
        self.description = tool_def.description
        self.input_schema = _build_pydantic_model(tool_def.name, tool_def.input_schema)
        self._client = client

    async def execute(self, input: BaseModel, ctx: SessionContext) -> ToolResult:
        try:
            raw = await self._client.call_tool(self.name, input.model_dump(exclude_none=True))
            return ToolResult(tool_use_id="", content=raw)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


def _resolve_env(value: str) -> str:
    if value.startswith("vault://"):
        return os.environ.get(value.replace("vault://", "VAULT_").upper(), "")
    return value


class MCPLoader:
    """Reads .mcp.json, starts MCP servers, and registers their tools."""

    def __init__(self, mcp_json_path: Path, registry: ToolRegistry) -> None:
        self._path = mcp_json_path
        self._registry = registry
        self._clients: list[MCPClient] = []
        self._resource_clients: dict[str, MCPClient] = {}
        self._resources_registered: bool = False

    async def load(self) -> None:
        if not self._path.exists():
            return

        config = json.loads(self._path.read_text(encoding="utf-8"))
        servers = list(config.get("mcpServers", {}).items())
        clients: list[MCPClient] = []

        # Build all clients first (no I/O)
        for server_name, server_cfg in servers:
            transport = server_cfg.get("transport", "stdio")
            if transport in ("sse", "http"):
                client = MCPClient(
                    name=server_name,
                    transport=transport,
                    url=server_cfg.get("url", ""),
                    headers=server_cfg.get("headers", {}),
                )
            else:
                env = {
                    key: _resolve_env(value)
                    for key, value in server_cfg.get("env", {}).items()
                }
                client = MCPClient(
                    name=server_name,
                    transport="stdio",
                    command=server_cfg["command"],
                    args=server_cfg.get("args", []),
                    env=env,
                )
            clients.append(client)

        # parallel_tool_discovery: start all clients concurrently
        start_results = await asyncio.gather(
            *[c.start() for c in clients], return_exceptions=True,
        )
        for c, r in zip(clients, start_results):
            if isinstance(r, BaseException):
                # Surface start failures without aborting other servers
                print(
                    f"[yigthinker.mcp] server '{c.name}' failed to start: "
                    f"{type(r).__name__}: {r}",
                    file=sys.stderr,
                )
        live_clients = [
            c for c, r in zip(clients, start_results)
            if not isinstance(r, BaseException)
        ]
        self._clients.extend(live_clients)

        # Discover tools concurrently
        tool_lists = await asyncio.gather(
            *[c.list_tools() for c in live_clients], return_exceptions=True,
        )

        # stable_tool_name_sort: flatten and sort by name for stable
        # LLM prompt-cache hits across runs.
        all_tool_pairs: list[tuple[MCPToolDef, MCPClient]] = []
        for client, tools in zip(live_clients, tool_lists):
            if isinstance(tools, BaseException):
                continue
            for t in tools:
                all_tool_pairs.append((t, client))
        all_tool_pairs.sort(key=lambda p: p[0].name)

        for tool_def, client in all_tool_pairs:
            self._registry.register(_MCPToolWrapper(tool_def, client))

        # Resource discovery (existing logic) — sequential is fine, runs after
        for client in live_clients:
            try:
                resources = await client.list_resources()
                if resources:
                    self._resource_clients[client.name] = client
            except Exception:
                pass

        if self._resource_clients and not self._resources_registered:
            from yigthinker.mcp.resource_tools import MCPListResourcesTool, MCPReadResourceTool
            self._registry.register(MCPListResourcesTool(self._resource_clients))
            self._registry.register(MCPReadResourceTool(self._resource_clients))
            self._resources_registered = True

    async def shutdown(self) -> None:
        for client in self._clients:
            try:
                await client.stop()
            except Exception:
                pass
        self._clients.clear()
