from __future__ import annotations

import json
import os
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

    async def load(self) -> None:
        if not self._path.exists():
            return

        config = json.loads(self._path.read_text(encoding="utf-8"))
        for server_name, server_cfg in config.get("mcpServers", {}).items():
            transport = server_cfg.get("transport", "stdio")

            if transport in ("sse", "http"):
                client = MCPClient(
                    name=server_name,
                    transport=transport,
                    url=server_cfg.get("url", ""),
                    headers=server_cfg.get("headers", {}),
                )
            else:
                # Default: stdio
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

            await client.start()
            self._clients.append(client)

            for tool_def in await client.list_tools():
                self._registry.register(_MCPToolWrapper(tool_def, client))

    async def shutdown(self) -> None:
        for client in self._clients:
            try:
                await client.stop()
            except Exception:
                pass
        self._clients.clear()
