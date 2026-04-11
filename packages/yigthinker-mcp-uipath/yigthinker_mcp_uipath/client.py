"""httpx.AsyncClient wrapper around UiPath Orchestrator OData v20.10+ endpoints.

Implemented in Plan 11-03 per CONTEXT.md D-12..D-14.

- **D-12:** Raw ``httpx.AsyncClient``, no UiPath SDK. Zero extra runtime deps.
- **D-13 (LOCKED constructor):** ``OrchestratorClient(auth, base_url)`` — exactly
  2 args. The ``httpx.AsyncClient`` is created INTERNALLY in ``__init__``.
  Callers NEVER pass an ``http`` kwarg. Plan 11-05 tool handlers match this.
- **D-13 retry:** 3 attempts with exponential backoff ``(1s, 2s, 4s)`` on 5xx
  and ``httpx.NetworkError``. 4xx fails immediately via ``raise_for_status()``.
  30s timeout per request.
- **D-14:** HTTP errors propagate to the tool handler layer (Plan 11-05), which
  converts them to ``ToolResult(is_error=True, content=...)``. This module does
  NOT swallow exceptions.

Per RESEARCH.md Finding 3 / Pitfall 2: every folder-scoped endpoint requires
the ``X-UIPATH-OrganizationUnitId`` header. Folder paths are resolved to
integer IDs via ``GET /odata/Folders?$filter=...``. The folder id is the
responsibility of the caller (tool handler) to pass to subsequent methods.

Per RESEARCH.md Finding 3 (ui_trigger_job critical note): ``start_job`` must
serialize ``InputArguments`` as a JSON STRING inside ``startInfo``, never as
a nested object — UiPath rejects StartJobs calls with nested JSON.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from yigthinker_mcp_uipath.auth import UipathAuth

RETRY_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0)
REQUEST_TIMEOUT_S: float = 30.0


class OrchestratorClient:
    """Thin async wrapper around UiPath Orchestrator OData endpoints.

    One client instance per ``call_tool`` invocation is the expected lifecycle;
    the Pitfall 4 thundering-herd fix lives inside ``UipathAuth`` via
    ``asyncio.Lock``, so sharing the auth object across clients is safe.
    """

    def __init__(self, auth: UipathAuth, base_url: str) -> None:
        # D-13 LOCKED: exactly 2 args. httpx.AsyncClient is internal.
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "OrchestratorClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal request helper with retry/backoff
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        folder_id: int | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Perform a request with auth headers, folder header, and retry.

        Retry semantics per D-13:
        - 3 attempts total (``RETRY_BACKOFFS`` is a 3-tuple).
        - Retry on 5xx responses and ``httpx.NetworkError``.
        - 4xx responses raise immediately via ``resp.raise_for_status()``.
        - Sleep ``RETRY_BACKOFFS[attempt]`` between attempts; the final
          attempt raises instead of sleeping.
        """
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{self.base_url}{path}"

        last_exc: Exception | None = None
        for attempt, backoff in enumerate(RETRY_BACKOFFS):
            is_last_attempt = attempt == len(RETRY_BACKOFFS) - 1
            try:
                headers = await self.auth.auth_headers(self._http)
                if folder_id is not None:
                    headers["X-UIPATH-OrganizationUnitId"] = str(folder_id)
                resp = await self._http.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                    files=files,
                )
            except httpx.NetworkError as exc:
                last_exc = exc
                if is_last_attempt:
                    raise
                await asyncio.sleep(backoff)
                continue

            if 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if is_last_attempt:
                    resp.raise_for_status()
                await asyncio.sleep(backoff)
                continue

            if 400 <= resp.status_code < 500:
                # D-13: 4xx fails immediately, no retry.
                resp.raise_for_status()

            return resp

        # Unreachable in practice — the loop either returns or raises above.
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Folder resolution (used by every other method)
    # ------------------------------------------------------------------

    async def resolve_folder_id(self, folder_path: str) -> int:
        """Resolve an Orchestrator folder path to its integer Id.

        Queries ``GET /odata/Folders?$filter=FullyQualifiedName eq '<path>'``.
        Raises ``ValueError`` if no folder matches. Per RESEARCH.md Open
        Question 3, this endpoint is organization-scoped (no folder header).
        """
        resp = await self._request(
            "GET",
            "/odata/Folders",
            params={
                "$filter": f"FullyQualifiedName eq '{folder_path}'",
                "$select": "Id",
            },
        )
        data = resp.json()
        value = data.get("value", [])
        if not value:
            raise ValueError(f"folder not found: {folder_path}")
        return int(value[0]["Id"])

    # ------------------------------------------------------------------
    # ui_deploy_process: upload package + create release
    # ------------------------------------------------------------------

    async def upload_package(
        self,
        folder_id: int,
        package_bytes: bytes,
        package_filename: str,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage",
            folder_id=folder_id,
            files={
                "file": (
                    package_filename,
                    package_bytes,
                    "application/octet-stream",
                )
            },
        )
        data = resp.json()
        value = data.get("value", [])
        if not value:
            raise ValueError("upload_package: empty response value")
        return dict(value[0])

    async def create_release(
        self,
        folder_id: int,
        workflow_name: str,
        version: str,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/odata/Releases",
            folder_id=folder_id,
            json_body={
                "Name": workflow_name,
                "ProcessKey": workflow_name,
                "ProcessVersion": version,
                "IsProcessDirty": False,
                "EnvironmentId": None,
                "Arguments": {"Input": None},
            },
        )
        return dict(resp.json())

    # ------------------------------------------------------------------
    # ui_trigger_job: release key lookup + start job
    # ------------------------------------------------------------------

    async def get_release_key_by_process(
        self,
        folder_id: int,
        process_key: str,
    ) -> str:
        """Resolve a process key to a release key for ``StartJobs``.

        Queries ``GET /odata/Releases?$filter=ProcessKey eq '<pk>'`` and
        returns the first matching release's ``Key``. Raises ``LookupError``
        if no release matches.
        """
        resp = await self._request(
            "GET",
            "/odata/Releases",
            folder_id=folder_id,
            params={"$filter": f"ProcessKey eq '{process_key}'"},
        )
        releases = resp.json().get("value", [])
        if not releases:
            raise LookupError(
                f"No release found for process_key={process_key!r}"
            )
        return str(releases[0]["Key"])

    async def start_job(
        self,
        folder_id: int,
        release_key: str,
        input_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # RESEARCH.md Finding 3 CRITICAL: InputArguments is a JSON STRING,
        # NOT a nested object. UiPath rejects StartJobs otherwise.
        input_args_str = json.dumps(input_arguments or {})
        resp = await self._request(
            "POST",
            "/odata/Jobs/UiPath.Server.Jobs.StartJobs",
            folder_id=folder_id,
            json_body={
                "startInfo": {
                    "ReleaseKey": release_key,
                    "Strategy": "ModernJobsCount",
                    "JobsCount": 1,
                    "InputArguments": input_args_str,
                }
            },
        )
        data = resp.json()
        value = data.get("value", [])
        if not value:
            raise ValueError("start_job: empty response value")
        return dict(value[0])

    # ------------------------------------------------------------------
    # ui_job_history
    # ------------------------------------------------------------------

    async def list_jobs(
        self,
        folder_id: int,
        release_key: str | None,
        top: int = 10,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "$orderby": "StartTime desc",
            "$top": top,
        }
        if release_key:
            params["$filter"] = f"Release/Key eq '{release_key}'"
        resp = await self._request(
            "GET",
            "/odata/Jobs",
            folder_id=folder_id,
            params=params,
        )
        data = resp.json()
        return list(data.get("value", []))

    # ------------------------------------------------------------------
    # ui_manage_trigger: schedule lookup + CRUD
    # ------------------------------------------------------------------

    async def get_schedule_id_by_name(
        self,
        folder_id: int,
        trigger_name: str,
    ) -> int:
        """Resolve a schedule name to its ProcessSchedules Id.

        Queries ``GET /odata/ProcessSchedules?$filter=Name eq '<name>'`` and
        returns the first matching schedule's ``Id``. Raises ``LookupError``
        if no schedule matches. The folder header is injected because
        ProcessSchedules is a folder-scoped collection (Pitfall 2).
        """
        resp = await self._request(
            "GET",
            "/odata/ProcessSchedules",
            folder_id=folder_id,
            params={"$filter": f"Name eq '{trigger_name}'"},
        )
        schedules = resp.json().get("value", [])
        if not schedules:
            raise LookupError(
                f"No schedule found for name={trigger_name!r}"
            )
        return int(schedules[0]["Id"])

    async def create_schedule(
        self,
        folder_id: int,
        name: str,
        release_key: str,
        cron: str,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/odata/ProcessSchedules",
            folder_id=folder_id,
            json_body={
                "Name": name,
                "ReleaseKey": release_key,
                "StartProcessCron": cron,
                "TimeZoneId": "UTC",
                "Enabled": True,
                "StartStrategy": 0,
            },
        )
        return dict(resp.json())

    async def update_schedule(
        self,
        folder_id: int,
        schedule_id: int,
        enabled: bool,
    ) -> dict[str, Any]:
        resp = await self._request(
            "PATCH",
            f"/odata/ProcessSchedules({schedule_id})",
            folder_id=folder_id,
            json_body={"Enabled": enabled},
        )
        # PATCH may return 204 No Content or the updated entity body.
        if resp.status_code == 204 or not resp.content:
            return {"Id": schedule_id, "Enabled": enabled}
        return dict(resp.json())

    async def delete_schedule(
        self,
        folder_id: int,
        schedule_id: int,
    ) -> None:
        await self._request(
            "DELETE",
            f"/odata/ProcessSchedules({schedule_id})",
            folder_id=folder_id,
        )

    # ------------------------------------------------------------------
    # ui_queue_status
    # ------------------------------------------------------------------

    async def get_queue_id(self, folder_id: int, queue_name: str) -> int:
        resp = await self._request(
            "GET",
            "/odata/QueueDefinitions",
            folder_id=folder_id,
            params={
                "$filter": f"Name eq '{queue_name}'",
                "$select": "Id",
            },
        )
        data = resp.json()
        value = data.get("value", [])
        if not value:
            raise ValueError(f"queue not found: {queue_name}")
        return int(value[0]["Id"])

    async def get_queue_status_count(
        self,
        folder_id: int,
        queue_id: int,
        days_no: int = 7,
    ) -> dict[str, Any]:
        resp = await self._request(
            "GET",
            (
                "/odata/QueueItems/"
                "UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount"
                f"(queueDefinitionId={queue_id},daysNo={days_no})"
            ),
            folder_id=folder_id,
        )
        return dict(resp.json())
