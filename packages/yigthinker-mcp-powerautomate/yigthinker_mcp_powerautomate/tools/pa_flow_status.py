"""pa_flow_status -- Query recent runs for a flow.

Returns the N most recent flow run summaries from
``/flows/{flow_id}/runs`` endpoint.

D-17: HTTP errors converted to is_error dicts; never raised.
D-23: Required fields flow_id, environment_id; optional top.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..client import PowerAutomateClient


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


async def handle(input: PaFlowStatusInput, client: PowerAutomateClient) -> dict:
    """Query flow runs and return a list of run summaries."""
    try:
        runs = await client.list_flow_runs(
            input.environment_id,
            input.flow_id,
            input.top,
        )
        mapped = [
            {
                "run_id": r["name"],
                "status": r["properties"]["status"],
                "start_time": r["properties"].get("startTime"),
                "end_time": r["properties"].get("endTime"),
            }
            for r in runs
        ]
        return {
            "flow_id": input.flow_id,
            "environment_id": input.environment_id,
            "runs": mapped,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "tool": "pa_flow_status",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except Exception as exc:
        return {
            "error": "internal_error",
            "tool": "pa_flow_status",
            "detail": str(exc),
        }
