"""pa_deploy_flow -- Deploy a notification-only HTTP Trigger -> Send Email (V2) flow.

Creates the flow in the specified Power Automate environment and returns the
flow_id and http_trigger_url. The trigger URL is the callback the user pastes
into config.yaml per design spec section 4.2.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaDeployFlowInput(BaseModel):
    """Deploy a notification-only email flow to Power Automate."""

    flow_name: str = Field(
        ...,
        description="Logical name for the flow (becomes the display name)",
    )
    environment_id: str = Field(
        ...,
        description="Power Automate environment ID to deploy into",
    )
    recipients: list[str] = Field(
        ...,
        description="Email addresses to receive notifications",
    )
    subject_template: str = Field(
        default="{workflow_name} notification",
        description="Email subject template; {workflow_name} is replaced at runtime",
    )
    display_name: str | None = Field(
        default=None,
        description="Optional display name; defaults to flow_name",
    )


async def handle(input: PaDeployFlowInput, client: Any) -> dict:
    """Deploy the notification flow and return flow_id + http_trigger_url."""
    raise NotImplementedError("Plan 12-05 replaces this")
