from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Module-level imports so test patches (patch("yigthinker.mcp.client.X")) work correctly.
# Each import is guarded separately since older MCP SDK versions may lack sse/streamable_http.
try:
    from mcp import ClientSession
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]

try:
    from mcp.client.sse import sse_client
except ImportError:
    sse_client = None  # type: ignore[assignment]

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    streamablehttp_client = None  # type: ignore[assignment]


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    """Manages one MCP server and exposes its tools.

    Supports three transports:
    - "stdio": subprocess (default, existing behaviour)
    - "sse":   HTTP SSE endpoint
    - "http":  Streamable HTTP endpoint
    """

    def __init__(
        self,
        name: str,
        transport: Literal["stdio", "sse", "http"] = "stdio",
        # stdio params
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        # sse / http params
        url: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self._transport = transport
        self._command = command
        self._args = args or []
        self._env = env or {}
        self._url = url
        self._headers = headers or {}
        self._session = None
        self._cm = None

    async def start(self) -> None:
        if self._transport == "stdio":
            params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=self._env or None,
            )
            self._cm = stdio_client(params)
            read, write = await self._cm.__aenter__()

        elif self._transport == "sse":
            self._cm = sse_client(self._url, headers=self._headers)
            read, write = await self._cm.__aenter__()

        elif self._transport == "http":
            self._cm = streamablehttp_client(self._url, headers=self._headers)
            read, write, _ = await self._cm.__aenter__()

        else:
            raise ValueError(f"Unknown MCP transport: {self._transport!r}")

        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._cm is not None:
            await self._cm.__aexit__(None, None, None)
            self._cm = None

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
