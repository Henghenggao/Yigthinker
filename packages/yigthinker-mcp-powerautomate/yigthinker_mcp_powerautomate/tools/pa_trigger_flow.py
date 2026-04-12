"""pa_trigger_flow -- Manually invoke a flow via its HTTP trigger.

Sends a POST to the flow's HTTP trigger URL with optional input payload.
Returns the run status and run_id.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


async def handle(input: PaTriggerFlowInput, client: Any) -> dict:
    """Trigger the flow and return run status + run_id."""
    raise NotImplementedError("Plan 12-05 replaces this")
