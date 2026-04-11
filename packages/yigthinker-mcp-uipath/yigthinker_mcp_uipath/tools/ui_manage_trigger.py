"""ui_manage_trigger — CRUD schedules (cron triggers) for a process.

Action dispatch via a ``Literal["create", "pause", "resume", "delete"]``
field. ``create`` needs both ``cron`` and ``trigger_name``; the other three
need ``trigger_name`` to look up the schedule id via the Plan 11-03 helper.

Cross-field validation (missing cron / missing trigger_name) fires BEFORE
any HTTP call so the handler short-circuits loudly on bad input.
"""
from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, Field

from ..client import OrchestratorClient


class UiManageTriggerInput(BaseModel):
    process_key: str
    action: Literal["create", "pause", "resume", "delete"]
    folder_path: str = Field(default="Shared")
    cron: str | None = Field(
        default=None,
        description="Required for action=create; UiPath cron format",
    )
    trigger_name: str | None = Field(
        default=None,
        description="Name of the schedule (required for every action)",
    )


async def handle(
    input: UiManageTriggerInput, client: OrchestratorClient
) -> dict:
    # Cross-field validation BEFORE any HTTP — short-circuit bad input.
    if input.action == "create" and input.cron is None:
        return {"error": "missing_cron", "action": "create"}
    if input.trigger_name is None:
        return {
            "error": "missing_trigger_name",
            "action": input.action,
        }

    try:
        folder_id = await client.resolve_folder_id(input.folder_path)
    except ValueError:
        return {
            "error": "folder_not_found",
            "folder_path": input.folder_path,
        }

    try:
        if input.action == "create":
            # Cron already validated above, but narrow the type for mypy.
            assert input.cron is not None
            try:
                release_key = await client.get_release_key_by_process(
                    folder_id, input.process_key
                )
            except LookupError:
                return {
                    "error": "release_not_found",
                    "process_key": input.process_key,
                }
            result = await client.create_schedule(
                folder_id=folder_id,
                name=input.trigger_name,
                release_key=release_key,
                cron=input.cron,
            )
            return {
                "status": "created",
                "schedule_id": result.get("Id"),
                "process_key": input.process_key,
                "action": "create",
            }

        # pause / resume / delete: resolve schedule id by name first.
        try:
            schedule_id = await client.get_schedule_id_by_name(
                folder_id, input.trigger_name
            )
        except LookupError:
            return {
                "error": "trigger_not_found",
                "trigger_name": input.trigger_name,
            }

        if input.action == "pause":
            await client.update_schedule(
                folder_id=folder_id,
                schedule_id=schedule_id,
                enabled=False,
            )
            return {
                "status": "paused",
                "schedule_id": schedule_id,
                "action": "pause",
            }
        if input.action == "resume":
            await client.update_schedule(
                folder_id=folder_id,
                schedule_id=schedule_id,
                enabled=True,
            )
            return {
                "status": "resumed",
                "schedule_id": schedule_id,
                "action": "resume",
            }
        if input.action == "delete":
            await client.delete_schedule(
                folder_id=folder_id, schedule_id=schedule_id
            )
            return {
                "status": "deleted",
                "schedule_id": schedule_id,
                "action": "delete",
            }

        # Literal type prevents this, but keep it defensive.
        return {"error": "unknown_action", "action": input.action}

    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
