"""pa_pause_flow -- Disable or enable a flow.

POSTs to ``/flows/{flow_id}/{action}`` to toggle the flow's enabled state.

D-17: HTTP errors converted to is_error dicts; never raised.
D-23: Required fields flow_id, environment_id, action.
"""
from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, Field

from ..client import PowerAutomateClient


class PaPauseFlowInput(BaseModel):
    """Disable or enable a Power Automate flow."""

    flow_id: str = Field(
        ...,
        description="The flow identifier to modify",
    )
    environment_id: str = Field(
        ...,
        description="Power Automate environment ID",
    )
    action: Literal["disable", "enable"] = Field(
        ...,
        description="Action to perform: 'disable' to pause, 'enable' to resume",
    )


async def handle(input: PaPauseFlowInput, client: PowerAutomateClient) -> dict:
    """Toggle flow state and return the resulting status."""
    try:
        if input.action == "disable":
            await client.stop_flow(input.environment_id, input.flow_id)
        else:
            await client.start_flow(input.environment_id, input.flow_id)
        return {
            "flow_id": input.flow_id,
            "environment_id": input.environment_id,
            "action": input.action,
            "result": "success",
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "tool": "pa_pause_flow",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except Exception as exc:
        return {
            "error": "internal_error",
            "tool": "pa_pause_flow",
            "detail": str(exc),
        }
