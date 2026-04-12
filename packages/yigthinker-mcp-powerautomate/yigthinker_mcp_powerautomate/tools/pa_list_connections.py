"""pa_list_connections -- List connections in a Power Automate environment.

Queries ``/connections`` endpoint, optionally filtered by connector name.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


async def handle(input: PaListConnectionsInput, client: Any) -> dict:
    """List connections and return a list of connection summaries."""
    raise NotImplementedError("Plan 12-05 replaces this")
