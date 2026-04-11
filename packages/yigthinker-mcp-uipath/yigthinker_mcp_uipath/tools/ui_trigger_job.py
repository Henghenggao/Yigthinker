"""ui_trigger_job — Start a job for an existing Release via OData StartJobs.

Resolves ``process_key`` to a ``release_key`` via the helper owned by
Plan 11-03, then posts the StartJobs body. Per Finding 3 / Pitfall 1 the
``InputArguments`` field MUST be serialized as a JSON STRING — the client's
``start_job`` handles that internally, so this handler simply passes the
dict through.

D-14 error handling: HTTP + folder/release lookup failures are converted to
dict returns, never raised.
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..client import OrchestratorClient


class UiTriggerJobInput(BaseModel):
    process_key: str = Field(
        ...,
        description=(
            "Release ProcessKey (same as workflow_name from deploy)"
        ),
    )
    folder_path: str = Field(default="Shared")
    input_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Arguments passed to the Python entry point — serialized to "
            "JSON string per UiPath OData spec"
        ),
    )


async def handle(
    input: UiTriggerJobInput, client: OrchestratorClient
) -> dict:
    try:
        folder_id = await client.resolve_folder_id(input.folder_path)
    except ValueError:
        return {"error": "folder_not_found", "folder_path": input.folder_path}

    try:
        release_key = await client.get_release_key_by_process(
            folder_id, input.process_key
        )
    except LookupError:
        return {
            "error": "release_not_found",
            "process_key": input.process_key,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }

    try:
        # client.start_job handles json.dumps(input_arguments) internally
        # (Finding 3).
        result = await client.start_job(
            folder_id=folder_id,
            release_key=release_key,
            input_arguments=input.input_arguments,
        )
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except ValueError as exc:
        return {
            "error": "no_job_started",
            "process_key": input.process_key,
            "detail": str(exc),
        }

    # client.start_job returns the first job dict directly (extracted from
    # the OData {"value": [...]} envelope).
    return {
        "job_id": result.get("Id"),
        "state": result.get("State", "Unknown"),
        "process_key": input.process_key,
    }
