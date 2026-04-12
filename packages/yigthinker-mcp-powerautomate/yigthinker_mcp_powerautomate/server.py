"""MCP low-level stdio server for Power Automate Flow Management integration.

Uses :class:`mcp.server.lowlevel.Server` (NOT FastMCP) because core Yigthinker's
``_MCPToolWrapper`` only understands :class:`TextContent` blocks (Phase 11
RESEARCH.md Finding 6). Tool results are serialized as a single ``TextContent.text``
block containing ``json.dumps(handler_result)`` per D-24.

Architectural invariants (locked decisions):

- **D-02:** low-level ``Server``, not FastMCP.
- **D-09:** :class:`PowerAutomateAuth` uses MSAL ConfidentialClientApplication.
- **D-15:** this module MUST NOT import anything from the core ``yigthinker``
  package (architect-not-executor invariant).
- **D-24 + Finding 6:** every ``call_tool`` response is a single
  ``[TextContent(type="text", text=json.dumps(result))]`` list.
"""
from __future__ import annotations


def build_server(config: object) -> object:
    """Construct a configured low-level MCP :class:`Server`.

    Stub — Plan 12-06 replaces this with the real implementation.
    """
    raise NotImplementedError("Plan 12-06 replaces this")


async def run_stdio() -> None:
    """Boot the MCP server on stdio transport.

    Stub — Plan 12-06 replaces this with the real implementation.
    """
    raise NotImplementedError("Plan 12-06 replaces this")


__all__ = ["build_server", "run_stdio"]
