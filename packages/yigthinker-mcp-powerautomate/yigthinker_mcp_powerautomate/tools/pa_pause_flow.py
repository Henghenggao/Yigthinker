"""pa_pause_flow -- Disable or enable a flow.

POSTs to ``/flows/{flow_id}/{action}`` to toggle the flow's enabled state.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


async def handle(input: PaPauseFlowInput, client: Any) -> dict:
    """Toggle flow state and return the resulting status."""
    raise NotImplementedError("Plan 12-05 replaces this")
