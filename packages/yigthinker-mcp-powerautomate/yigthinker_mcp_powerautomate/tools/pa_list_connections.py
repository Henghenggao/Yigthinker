"""pa_list_connections -- List connections in a Power Automate environment.

Queries ``/connections`` endpoint, optionally filtered by connector name.

D-17: HTTP errors converted to is_error dicts; never raised.
D-23/D-25: Fully implemented, not stubbed.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..client import PowerAutomateClient


class PaListConnectionsInput(BaseModel):
    """List available connections in a Power Automate environment."""

    environment_id: str = Field(
        ...,
        description="Power Automate environment ID",
    )
    connector_name: str | None = Field(
        default=None,
        description="Optional connector name to filter by (e.g. 'shared_office365')",
    )


async def handle(input: PaListConnectionsInput, client: PowerAutomateClient) -> dict:
    """List connections and return a list of connection summaries."""
    try:
        connections = await client.list_connections(
            input.environment_id,
            input.connector_name,
        )
        mapped = [
            {
                "connection_id": c["name"],
                "display_name": c.get("properties", {}).get("displayName", ""),
                "connector": c.get("properties", {}).get("apiId", ""),
                "statuses": c.get("properties", {}).get("statuses", []),
            }
            for c in connections
        ]
        return {
            "environment_id": input.environment_id,
            "connections": mapped,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "tool": "pa_list_connections",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except Exception as exc:
        return {
            "error": "internal_error",
            "tool": "pa_list_connections",
            "detail": str(exc),
        }
