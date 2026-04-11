"""Low-level MCP stdio server. Wired in Plan 11-06.

Will use ``mcp.server.lowlevel.Server`` + ``mcp.server.stdio.stdio_server``
per RESEARCH.md Pattern 1. Tool dispatch reads from
``yigthinker_mcp_uipath.tools.TOOL_REGISTRY``.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "yigthinker_mcp_uipath.server.main is wired in Plan 11-06"
    )
