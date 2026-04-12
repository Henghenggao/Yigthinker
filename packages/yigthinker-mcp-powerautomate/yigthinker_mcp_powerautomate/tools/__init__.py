"""Power Automate MCP tool registry (populated by Plan 12-05).

Maps tool name -> ``(input_model, handler)`` tuples. ``server.py``
(Plan 12-06) iterates this at startup to register tools with the low-level
MCP Server.

Per CONTEXT.md D-23 the 5 tools are:

- ``pa_deploy_flow`` -- deploy notification-only HTTP Trigger -> Send Email flow
- ``pa_trigger_flow`` -- manually invoke a flow via its HTTP trigger
- ``pa_flow_status`` -- query recent runs for a flow
- ``pa_pause_flow`` -- disable or enable a flow
- ``pa_list_connections`` -- list connections in an environment
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel

Handler = Callable[[BaseModel, Any], Awaitable[dict]]

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Handler]] = {}

__all__ = ["TOOL_REGISTRY"]
