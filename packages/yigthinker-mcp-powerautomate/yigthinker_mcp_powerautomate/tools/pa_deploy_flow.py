"""pa_deploy_flow -- Deploy a notification-only HTTP Trigger -> Send Email (V2) flow.

Creates the flow in the specified Power Automate environment and returns the
flow_id and http_trigger_url. The trigger URL is the callback the user pastes
into config.yaml per design spec section 4.2.

D-19/D-22: Calls flow_builder.build_notification_flow_clientdata, then
client.create_flow, then client.get_flow (fallback for trigger URL).
D-17: HTTP errors converted to is_error dicts; never raised.
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..client import PowerAutomateClient
from ..flow_builder import build_notification_flow_clientdata


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


async def handle(input: PaDeployFlowInput, client: PowerAutomateClient) -> dict:
    """Deploy the notification flow and return flow_id + http_trigger_url."""
    try:
        # Step 1: Build clientdata from the flow builder (D-19/D-20).
        clientdata = build_notification_flow_clientdata(
            flow_name=input.flow_name,
            recipients=input.recipients,
            subject_template=input.subject_template,
            display_name=input.display_name,
        )

        # Step 2: Build request body for create_flow.
        body: dict[str, Any] = {
            "properties": {
                "displayName": input.display_name or input.flow_name,
                "definition": clientdata["properties"]["definition"],
                "connectionReferences": clientdata["properties"]["connectionReferences"],
                "state": "Started",
            },
        }

        # Step 3: Create the flow.
        resp = await client.create_flow(input.environment_id, body)

        # Step 4: Extract flow_id.
        flow_id: str = resp["name"]

        # Step 5: Try to get trigger URL from create response; fall back to get_flow.
        trigger_url = resp.get("properties", {}).get("flowTriggerUri")
        if trigger_url is None:
            flow_detail = await client.get_flow(input.environment_id, flow_id)
            trigger_url = flow_detail.get("properties", {}).get("flowTriggerUri", "")

        # Step 6: Return per D-22.
        return {
            "flow_id": flow_id,
            "http_trigger_url": trigger_url,
            "flow_name": input.flow_name,
            "environment_id": input.environment_id,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "tool": "pa_deploy_flow",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except Exception as exc:
        return {
            "error": "internal_error",
            "tool": "pa_deploy_flow",
            "detail": str(exc),
        }
