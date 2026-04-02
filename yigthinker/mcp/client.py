from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    """Manages one MCP server process and exposes its tools."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self._command = command
        self._args = args
        self._env = env or {}
        self._session = None
        self._stdio_cm = None

    async def start(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env or None,
        )
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(None, None, None)
            self._stdio_cm = None

    async def list_tools(self) -> list[MCPToolDef]:
        if self._session is None:
            raise RuntimeError(f"MCPClient '{self.name}' not started. Call start() first.")
        result = await self._session.list_tools()
        return [
            MCPToolDef(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in result.tools
        ]

    async def call_tool(self, tool_name: str, tool_input: dict) -> str:
        if self._session is None:
            raise RuntimeError(f"MCPClient '{self.name}' not started. Call start() first.")
        result = await self._session.call_tool(tool_name, tool_input)
        parts = [block.text for block in result.content if hasattr(block, "text")]
        return "\n".join(parts)
