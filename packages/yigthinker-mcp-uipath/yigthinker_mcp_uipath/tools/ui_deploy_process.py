"""ui_deploy_process — Build .nupkg, upload to Orchestrator, create Release.

Composes nupkg.build_nupkg + OrchestratorClient.upload_package +
OrchestratorClient.create_release into a single atomic deploy. D-14 error
handling: HTTP errors are converted to ``{"error": "http_error", ...}``
dicts; no exceptions escape the handler.
"""
from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from ..client import OrchestratorClient
from ..nupkg import build_nupkg


class UiDeployProcessInput(BaseModel):
    workflow_name: str = Field(
        ...,
        description=(
            "Logical workflow name; becomes the package id and the UiPath "
            "process key"
        ),
    )
    script_path: str = Field(
        ...,
        description=(
            "Absolute path to the Python entry script on the local "
            "filesystem"
        ),
    )
    folder_path: str = Field(
        default="Shared",
        description="UiPath Orchestrator folder FullyQualifiedName",
    )
    package_version: str = Field(
        default="1.0.0", description="SemVer for the uploaded package"
    )


async def handle(
    input: UiDeployProcessInput, client: OrchestratorClient
) -> dict:
    try:
        script = Path(input.script_path)
        if not script.is_file():
            return {
                "error": "script_not_found",
                "script_path": input.script_path,
            }

        folder_id = await client.resolve_folder_id(input.folder_path)
        nupkg_bytes = build_nupkg(
            script, input.workflow_name, input.package_version
        )
        filename = f"{input.workflow_name}.{input.package_version}.nupkg"

        await client.upload_package(
            folder_id=folder_id,
            package_bytes=nupkg_bytes,
            package_filename=filename,
        )
        release = await client.create_release(
            folder_id=folder_id,
            workflow_name=input.workflow_name,
            version=input.package_version,
        )
        return {
            "status": "deployed",
            "process_key": input.workflow_name,
            "release_key": release.get("Key"),
            "folder_path": input.folder_path,
            "package_version": input.package_version,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except ValueError as exc:
        return {
            "error": "folder_not_found",
            "folder_path": input.folder_path,
            "detail": str(exc),
        }
