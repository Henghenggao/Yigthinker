from __future__ import annotations

import asyncio
import hmac
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

        try:
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
        except BaseException:
            # Session init failed after transport opened; tear down transport.
            self._session = None
            if self._cm is not None:
                try:
                    await self._cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._cm = None
            raise

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
        try:
            result = await self._session.call_tool(tool_name, tool_input)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise
        except Exception:
            # auto_reconnect_on_tool_exec_failure — one retry with fresh session
            try:
                await self.stop()
            except Exception:
                pass
            await self.start()
            if self._session is None:
                raise RuntimeError(
                    f"MCPClient '{self.name}' failed to reconnect: session is None after start()"
                )
            result = await self._session.call_tool(tool_name, tool_input)
        parts = [block.text for block in result.content if hasattr(block, "text")]
        return "\n".join(parts)

    async def list_resources(self) -> list[dict[str, str]]:
        """List available resources from this MCP server."""
        if self._session is None:
            raise RuntimeError(f"MCPClient '{self.name}' not started. Call start() first.")
        try:
            result = await self._session.list_resources()
        except Exception:
            return []  # Server may not support resources
        return [
            {
                "uri": str(r.uri),
                "name": r.name or "",
                "description": getattr(r, "description", "") or "",
            }
            for r in result.resources
        ]

    async def read_resource(self, uri: str) -> str:
        """Read a specific resource by URI."""
        if self._session is None:
            raise RuntimeError(f"MCPClient '{self.name}' not started. Call start() first.")
        result = await self._session.read_resource(uri)
        parts = [c.text for c in result.contents if hasattr(c, "text")]
        return "\n".join(parts)


def constant_time_equal(a: str, b: str) -> bool:
    """Constant-time string comparison using ``hmac.compare_digest``.

    The comparison takes time proportional to the length of the shorter input
    and does not short-circuit on the first differing byte, which prevents
    timing side-channel attacks on secret comparisons (e.g. bearer tokens).
    Use this for any future MCP bearer-token auth.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
