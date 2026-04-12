"""pa_flow_status -- Query recent runs for a flow.

Returns the N most recent flow run summaries from
``/flows/{flow_id}/runs`` endpoint.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaFlowStatusInput(BaseModel):
    """Get recent run history for a Power Automate flow."""

    flow_id: str = Field(
        ...,
        description="The flow identifier to query runs for",
    )
    environment_id: str = Field(
        ...,
        description="Power Automate environment ID",
    )
    top: int = Field(
        default=10,
        description="Maximum number of recent runs to return",
    )


async def handle(input: PaFlowStatusInput, client: Any) -> dict:
    """Query flow runs and return a list of run summaries."""
    raise NotImplementedError("Plan 12-05 replaces this")
