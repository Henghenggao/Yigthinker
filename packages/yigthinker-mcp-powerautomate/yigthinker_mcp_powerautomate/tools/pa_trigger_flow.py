"""pa_trigger_flow -- Manually invoke a flow via its HTTP trigger.

Sends a POST to the flow's HTTP trigger URL with optional input payload.
Returns the run status and run_id.

D-17: HTTP errors converted to is_error dicts; never raised.
D-23: Required fields flow_id, environment_id; optional trigger_input.
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..client import PowerAutomateClient


class PaTriggerFlowInput(BaseModel):
    """Manually trigger a Power Automate flow run."""

    flow_id: str = Field(
        ...,
        description="The flow identifier to trigger",
    )
    environment_id: str = Field(
        ...,
        description="Power Automate environment ID",
    )
    trigger_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional JSON payload passed to the flow trigger",
    )


async def handle(input: PaTriggerFlowInput, client: PowerAutomateClient) -> dict:
    """Trigger the flow and return run status + run_id."""
    try:
        resp = await client.trigger_flow_run(
            input.environment_id,
            input.flow_id,
            input.trigger_input,
        )
        return {
            "flow_id": input.flow_id,
            "run_id": resp.get("name", ""),
            "status": resp.get("properties", {}).get("status", ""),
            "environment_id": input.environment_id,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "tool": "pa_trigger_flow",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except Exception as exc:
        return {
            "error": "internal_error",
            "tool": "pa_trigger_flow",
            "detail": str(exc),
        }
