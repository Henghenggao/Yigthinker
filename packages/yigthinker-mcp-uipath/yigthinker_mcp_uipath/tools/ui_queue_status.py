"""ui_queue_status — Return item counts per state for a queue.

Calls ``client.get_queue_id`` to resolve name -> integer id, then
``client.get_queue_status_count`` which hits the modern Orchestrator OData
path ``/odata/QueueItems/UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount``
(NOT the legacy ``GetQueueItemsCounts`` typo — see RESEARCH.md Finding 3 /
MEDIUM 2 guard).

Maps Orchestrator's PascalCase ``{New, InProgress, Failed, Successful}``
dict to snake_case output keys the LLM can consume verbatim.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..client import OrchestratorClient


class UiQueueStatusInput(BaseModel):
    queue_name: str
    folder_path: str = Field(default="Shared")


async def handle(
    input: UiQueueStatusInput, client: OrchestratorClient
) -> dict:
    try:
        folder_id = await client.resolve_folder_id(input.folder_path)
    except ValueError:
        return {
            "error": "folder_not_found",
            "folder_path": input.folder_path,
        }

    try:
        queue_id = await client.get_queue_id(
            folder_id=folder_id, queue_name=input.queue_name
        )
    except ValueError:
        # client.get_queue_id raises ValueError("queue not found: ...")
        # when the filter returns an empty list.
        return {"error": "queue_not_found", "queue_name": input.queue_name}
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }

    try:
        counts = await client.get_queue_status_count(
            folder_id=folder_id, queue_id=queue_id
        )
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }

    return {
        "queue_name": input.queue_name,
        "new": counts.get("New", 0),
        "in_progress": counts.get("InProgress", 0),
        "failed": counts.get("Failed", 0),
        "successful": counts.get("Successful", 0),
    }
