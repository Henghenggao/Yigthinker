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

from .pa_deploy_flow import PaDeployFlowInput
from .pa_deploy_flow import handle as _deploy
from .pa_flow_status import PaFlowStatusInput
from .pa_flow_status import handle as _status
from .pa_list_connections import PaListConnectionsInput
from .pa_list_connections import handle as _connections
from .pa_pause_flow import PaPauseFlowInput
from .pa_pause_flow import handle as _pause
from .pa_trigger_flow import PaTriggerFlowInput
from .pa_trigger_flow import handle as _trigger

Handler = Callable[[BaseModel, Any], Awaitable[dict]]

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Handler]] = {
    "pa_deploy_flow": (PaDeployFlowInput, _deploy),
    "pa_trigger_flow": (PaTriggerFlowInput, _trigger),
    "pa_flow_status": (PaFlowStatusInput, _status),
    "pa_pause_flow": (PaPauseFlowInput, _pause),
    "pa_list_connections": (PaListConnectionsInput, _connections),
}

__all__ = ["TOOL_REGISTRY"]
