"""Tool handlers for the 5 UiPath MCP tools (CONTEXT.md D-19).

Plan 11-05 fills in the 5 handlers and the TOOL_REGISTRY mapping.
Plan 11-06 imports TOOL_REGISTRY from here to wire the dispatch.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

# Populated in Plan 11-05 — name -> (mcp.types.Tool, async handler).
TOOL_REGISTRY: dict[str, tuple[Any, Callable[..., Awaitable[Any]]]] = {}
