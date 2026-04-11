"""ui_job_history — List recent jobs for a process.

Resolves ``process_key`` to ``release_key`` via the Plan 11-03 helper, then
calls ``client.list_jobs`` which filters OData ``/Jobs`` by
``Release/Key eq '<release_key>'``. Shapes the raw Orchestrator entities
into a compact summary payload for the LLM.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..client import OrchestratorClient


class UiJobHistoryInput(BaseModel):
    process_key: str = Field(
        ..., description="Release ProcessKey to filter jobs by"
    )
    folder_path: str = Field(default="Shared")
    top: int = Field(default=10, ge=1, le=100)


async def handle(
    input: UiJobHistoryInput, client: OrchestratorClient
) -> dict:
    try:
        folder_id = await client.resolve_folder_id(input.folder_path)
    except ValueError:
        return {
            "error": "folder_not_found",
            "folder_path": input.folder_path,
        }

    try:
        release_key = await client.get_release_key_by_process(
            folder_id, input.process_key
        )
    except LookupError:
        # No release for this process yet — return empty history rather
        # than error.
        return {
            "process_key": input.process_key,
            "count": 0,
            "jobs": [],
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }

    try:
        jobs = await client.list_jobs(
            folder_id=folder_id,
            release_key=release_key,
            top=input.top,
        )
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }

    return {
        "process_key": input.process_key,
        "count": len(jobs),
        "jobs": [
            {
                "id": j.get("Id"),
                "state": j.get("State"),
                "start_time": j.get("StartTime"),
                "end_time": j.get("EndTime"),
                "info": j.get("Info"),
            }
            for j in jobs
        ],
    }
