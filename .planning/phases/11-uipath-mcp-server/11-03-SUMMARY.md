---
phase: 11-uipath-mcp-server
plan: 03
subsystem: uipath-mcp-package
tags: [httpx, orchestrator, odata, retry, folder-header, tdd, wave-1]
wave: 1
requirements: [MCP-UI-01]
one_liner: "OrchestratorClient async httpx wrapper around 10 UiPath Orchestrator OData endpoints with 3-attempt retry, folder-header injection, release/schedule lookups, and InputArguments JSON-string serialization"
dependency_graph:
  requires:
    - "11-01 (yigthinker_mcp_uipath package scaffold + conftest SAMPLE_BASE_URL/SAMPLE_TOKEN_URL constants)"
    - "11-02 (UipathAuth.auth_headers for Bearer token injection)"
  provides:
    - "OrchestratorClient class importable from yigthinker_mcp_uipath.client"
    - "RETRY_BACKOFFS = (1.0, 2.0, 4.0) constant for downstream retry tuning"
    - "REQUEST_TIMEOUT_S = 30.0 constant for per-request timeout budget"
    - "12 async methods: resolve_folder_id, upload_package, create_release, get_release_key_by_process, start_job, list_jobs, get_schedule_id_by_name, create_schedule, update_schedule, delete_schedule, get_queue_id, get_queue_status_count"
    - "_request internal helper handling auth header, X-UIPATH-OrganizationUnitId, retry on 5xx/NetworkError, 4xx immediate fail"
  affects:
    - "Plan 11-05 tool handlers (ui_deploy_process uses upload_package + create_release; ui_trigger_job uses get_release_key_by_process + start_job; ui_job_history uses list_jobs; ui_manage_trigger uses get_schedule_id_by_name + create/update/delete_schedule; ui_queue_status uses get_queue_id + get_queue_status_count)"
    - "Plan 11-05 MUST NOT list client.py in its files_modified (ownership transfer)"
tech_stack:
  added:
    - "None — httpx is already declared in Plan 11-01 pyproject.toml core deps"
  patterns:
    - "Async context manager (__aenter__/__aexit__) for lifetime management"
    - "Internal httpx.AsyncClient created eagerly in __init__ (D-13 — no http kwarg)"
    - "Retry loop with enumerate(RETRY_BACKOFFS) + is_last_attempt early-exit for 5xx / NetworkError"
    - "httpx.HTTPStatusError re-raised via resp.raise_for_status() for 4xx"
    - "InputArguments as JSON string (json.dumps) inside startInfo per RESEARCH.md Finding 3 critical note"
    - "Folder-scoped header (X-UIPATH-OrganizationUnitId) injected per-request when folder_id is provided"
    - "OData $filter string building with f-strings (no URL param library needed)"
    - "LookupError for missing release/schedule, ValueError for missing folder/queue (distinct error classes for handler dispatch in Plan 11-05)"
key_files:
  created:
    - "packages/yigthinker-mcp-uipath/tests/test_client.py (575 lines, 19 tests)"
  modified:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/client.py (stub → 402-line implementation)"
decisions:
  - "D-13 constructor signature locked verbatim: OrchestratorClient(auth, base_url) — exactly 2 args, httpx.AsyncClient created internally in __init__, no http kwarg. Plan 11-05 handler tests match this shape."
  - "RESEARCH.md Open Question 3 disposition: resolve_folder_id does NOT inject the folder header (Folders is organization-scoped). All other folder-scoped helpers DO inject the header, including both lookup helpers (get_release_key_by_process, get_schedule_id_by_name)."
  - "Retry loop structure: 5xx path sleeps + continue + early-exit raise on last attempt; NetworkError path identical; 4xx always immediate raise (no retry); 2xx always immediate return. Avoids double-increment bugs by using enumerate(RETRY_BACKOFFS) with is_last_attempt check."
  - "LookupError (not ValueError) for missing release/schedule — distinct from ValueError-for-missing-folder/queue so Plan 11-05 handlers can map each to a specific tool-layer error message."
  - "Queue status OData path uses GetQueueItemsByStatusCount(queueDefinitionId=N,daysNo=N) per RESEARCH.md Finding 3 — NOT the legacy /odata/Queues/UiPathODataSvc.GetQueueItemsCounts form. Test 11 explicitly locks this URL literal."
  - "Finding 3 InputArguments critical behavior asserted both in production code (json.dumps(input_arguments or {})) and at the test layer (assert isinstance(body['startInfo']['InputArguments'], str))."
metrics:
  duration: "~10 minutes"
  completed: "2026-04-11"
  tasks: 2
  tests_added: 19
  tests_passing: 19
  files_created: 1
  files_modified: 1
---

# Phase 11 Plan 03: OrchestratorClient OData Wrapper Summary

Ship the `OrchestratorClient` async httpx wrapper that the 5 tool handlers in Plan 11-05 will build against. This is the single centralized place for UiPath Orchestrator OData v20.10+ HTTP logic in `yigthinker-mcp-uipath`: retry/backoff, folder header injection, auth header wiring, and the two lookup helpers (`get_release_key_by_process`, `get_schedule_id_by_name`) that let handlers accept user-facing names instead of internal UiPath GUIDs.

## What Was Built

### `OrchestratorClient` class (`packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/client.py`)

**D-13 locked constructor:**

```python
class OrchestratorClient:
    def __init__(self, auth: UipathAuth, base_url: str) -> None:
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)
```

Exactly 2 args. `httpx.AsyncClient` is created internally. No `http` kwarg. Plan 11-05 handler tests must match this shape.

**Module-level constants** (exported for retry-loop tests):

| Constant | Value |
|---|---|
| `RETRY_BACKOFFS` | `(1.0, 2.0, 4.0)` |
| `REQUEST_TIMEOUT_S` | `30.0` |

**12 async methods** — the full surface Plan 11-05 handlers need:

| Method | Tool | OData endpoint |
|---|---|---|
| `resolve_folder_id(folder_path)` | all 5 | `GET /odata/Folders?$filter=FullyQualifiedName eq '...'` |
| `upload_package(folder_id, bytes, filename)` | ui_deploy_process | `POST /odata/Processes/UiPath.Server.Configuration.OData.UploadPackage` (multipart) |
| `create_release(folder_id, workflow_name, version)` | ui_deploy_process | `POST /odata/Releases` |
| `get_release_key_by_process(folder_id, process_key)` | ui_trigger_job | `GET /odata/Releases?$filter=ProcessKey eq '...'` |
| `start_job(folder_id, release_key, input_arguments)` | ui_trigger_job | `POST /odata/Jobs/UiPath.Server.Jobs.StartJobs` |
| `list_jobs(folder_id, release_key, top)` | ui_job_history | `GET /odata/Jobs?$filter=Release/Key eq '...'&$orderby=StartTime desc&$top=N` |
| `get_schedule_id_by_name(folder_id, trigger_name)` | ui_manage_trigger | `GET /odata/ProcessSchedules?$filter=Name eq '...'` |
| `create_schedule(folder_id, name, release_key, cron)` | ui_manage_trigger | `POST /odata/ProcessSchedules` |
| `update_schedule(folder_id, schedule_id, enabled)` | ui_manage_trigger | `PATCH /odata/ProcessSchedules({id})` |
| `delete_schedule(folder_id, schedule_id)` | ui_manage_trigger | `DELETE /odata/ProcessSchedules({id})` |
| `get_queue_id(folder_id, queue_name)` | ui_queue_status | `GET /odata/QueueDefinitions?$filter=Name eq '...'` |
| `get_queue_status_count(folder_id, queue_id, days_no)` | ui_queue_status | `GET /odata/QueueItems/UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount(queueDefinitionId=N,daysNo=N)` |

**Internal `_request` helper** handles:

1. URL normalization (relative path vs absolute URL).
2. `UipathAuth.auth_headers(self._http)` call → `Authorization: Bearer <token>` injection.
3. Optional `X-UIPATH-OrganizationUnitId: <folder_id>` header when `folder_id` is passed (Pitfall 2 guard).
4. Retry loop: 3 attempts, exponential backoff `(1s, 2s, 4s)`, retry on 5xx and `httpx.NetworkError`, immediate fail on 4xx via `resp.raise_for_status()`.
5. Last-attempt early-exit: raises instead of sleeping.

### Test suite (`packages/yigthinker-mcp-uipath/tests/test_client.py`)

19 respx-mocked unit tests covering every locked contract:

| # | Test | What it proves |
|---|---|---|
| 1 | `test_resolve_folder_id_calls_filter_and_returns_int` | `GET /odata/Folders?$filter=FullyQualifiedName eq 'Shared'` → `42` |
| 2 | `test_resolve_folder_id_raises_on_empty` | Empty `value` array → `ValueError("folder not found")` |
| 3 | `test_upload_package_sends_folder_header_and_returns_process_key` | `X-UIPATH-OrganizationUnitId: 42` header present; returns `{"Key": "pk_abc", ...}` |
| 4 | `test_create_release_posts_release_body` | Body contains `ProcessKey`, `ProcessVersion`; folder header set |
| 5 | `test_start_job_serializes_input_arguments_as_json_string` | **Finding 3 critical:** `body["startInfo"]["InputArguments"]` is a `str`, not a `dict`; `Strategy == "ModernJobsCount"`, `JobsCount == 1` |
| 6 | `test_list_jobs_filters_by_release_key` | URL contains `Release/Key` (or URL-encoded `Release%2FKey`) + release key; folder header set |
| 7 | `test_create_schedule_posts_release_key_and_cron` | Body contains `Name`, `ReleaseKey`, `StartProcessCron`, `Enabled: true`, `TimeZoneId: "UTC"` |
| 8 | `test_update_schedule_patches_enabled_flag` | `PATCH` body is exactly `{"Enabled": false}` |
| 9 | `test_delete_schedule_returns_none` | `DELETE` 204 response → method returns `None`; folder header set |
| 10 | `test_get_queue_id_filters_by_name` | `GET /odata/QueueDefinitions?$filter=Name eq 'critical_q'` → `99` |
| 11 | `test_get_queue_status_count_returns_dict` | Correct OData URL `/odata/QueueItems/...GetQueueItemsByStatusCount(queueDefinitionId=7,daysNo=7)`; returns counts dict |
| 12 | `test_retry_on_5xx_then_succeed` | `500 → 503 → 200` → `call_count == 3`; `asyncio.sleep` monkeypatched to no-op |
| 13 | `test_retry_on_network_error_then_succeed` | `NetworkError → NetworkError → 200` → `call_count == 3` |
| 14 | `test_no_retry_on_4xx` | `404` → `raise HTTPStatusError` immediately; `call_count == 1` |
| 15 | `test_5xx_after_max_retries_raises` | `500 × 3` → `raise HTTPStatusError`; `call_count == 3` |
| 16 | `test_get_release_key_by_process_returns_key` | `GET /odata/Releases?$filter=ProcessKey eq 'test_flow'` → `"rk-abc-123"`; folder header set |
| 17 | `test_get_release_key_by_process_raises_on_empty` | Empty `value` → `LookupError("No release found")` |
| 18 | `test_get_schedule_id_by_name_returns_id` | `GET /odata/ProcessSchedules?$filter=Name eq 'nightly'` → `77`; folder header set |
| 19 | `test_get_schedule_id_by_name_raises_on_empty` | Empty `value` → `LookupError("No schedule found")` |

## Test Results

```
cd packages/yigthinker-mcp-uipath && python -m pytest tests/test_client.py -x
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.2, pluggy-1.6.0
configfile: pyproject.toml
plugins: anyio-4.13.0, dash-4.1.0, asyncio-1.3.0, mock-3.15.1, respx-0.23.1
collected 19 items

tests\test_client.py ...................                                 [100%]

============================= 19 passed in 3.41s ==============================
```

Full-package regression run (scaffold + auth + nupkg + client): `36 passed in 4.55s`.

## Commits

| Hash | Subject |
|---|---|
| `82af09f` | test(11-03): add failing test_client.py locking OrchestratorClient contracts |
| `a8ebe65` | feat(11-03): implement OrchestratorClient OData wrapper |

## Deviations from Plan

**None.** Both the test skeleton and the implementation were copied verbatim from the plan file with minor cosmetic expansion (e.g., adding the remaining 15 tests the plan skeleton abbreviated). No deviation rules triggered:

- No bugs to auto-fix (Rule 1)
- No missing critical functionality (Rule 2)
- No blocking issues (Rule 3)
- No architectural changes needed (Rule 4)

The `try/finally` + `await client.aclose()` pattern wrapped around each test's client use is a minor test-hygiene addition beyond the plan skeleton — it avoids ResourceWarning from the internal `httpx.AsyncClient` not being closed. This is a pure test-layer nicety and does not alter production code.

## Truth Checks (from plan `must_haves.truths`)

- [x] `OrchestratorClient` class exposes async methods that wrap each OData endpoint the 5 tools need
- [x] Constructor signature is exactly `(auth: UipathAuth, base_url: str)` per D-13 — no `http` arg
- [x] Retries: 3 attempts on 5xx and `httpx.NetworkError`, exponential backoff (1s/2s/4s) — verified by tests 12, 13, 15
- [x] 4xx responses raise immediately (no retry) — verified by test 14 (`call_count == 1`)
- [x] 30s timeout per request (`REQUEST_TIMEOUT_S = 30.0` passed to `httpx.AsyncClient(timeout=...)`)
- [x] Folder path resolved to integer folder id via `GET /odata/Folders?$filter=FullyQualifiedName eq '<path>'` (resolve_folder_id, test 1)
- [x] All folder-scoped requests inject `X-UIPATH-OrganizationUnitId: <folder_id>` header (Pitfall 2) — verified by tests 3, 4, 5, 6, 7, 8, 9, 10, 11, 16, 18
- [x] `get_release_key_by_process` resolves process key to release key for `StartJobs` via OData Releases filter — tests 16, 17
- [x] `get_schedule_id_by_name` resolves schedule name to `ProcessSchedules` Id via OData filter — tests 18, 19

## Artifacts (from plan `must_haves.artifacts`)

- [x] `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/client.py` — 402 lines (required ≥120), contains `class OrchestratorClient`
- [x] `packages/yigthinker-mcp-uipath/tests/test_client.py` — 575 lines (required ≥100), contains `test_retry_on_5xx_then_succeed` and all 18 other tests

## Key Links (from plan `must_haves.key_links`)

- [x] `OrchestratorClient._request` → `UipathAuth.auth_headers(self._http)` (Bearer token injection per request)
- [x] `OrchestratorClient.resolve_folder_id` → `GET /odata/Folders?$filter=FullyQualifiedName eq '<path>'`
- [x] `OrchestratorClient.get_release_key_by_process` → `GET /odata/Releases?$filter=ProcessKey eq '<pk>'` + `X-UIPATH-OrganizationUnitId` header
- [x] `OrchestratorClient.get_schedule_id_by_name` → `GET /odata/ProcessSchedules?$filter=Name eq '<name>'` + `X-UIPATH-OrganizationUnitId` header

## Known Stubs

**None.** `client.py` is fully implemented; zero `NotImplementedError`, zero placeholder returns, zero TODO comments.

## Deferred Issues

**None.**

## Open Question Disposition

**RESEARCH.md Open Question 3 — "Does the Folders endpoint require the X-UIPATH-OrganizationUnitId header?"** — Resolved as **NO**. `resolve_folder_id` is the only method in this module that does NOT set the folder header, because the Folders collection is organization-scoped (you query it precisely to discover folder ids). All other folder-scoped methods, including both new lookup helpers, DO inject the header. If live UAT later reveals that some tenants reject Folders queries without the header, the fix is local to `resolve_folder_id` and does not ripple.

## MCP-UI-01 Status

MCP-UI-01 is **partially implemented** at the HTTP-wrapper layer by this plan. End-to-end tool verification still requires:

- Plan 11-05 tool handlers (Wave 2) — wires each of the 5 tool Pydantic input schemas to this client
- Plan 11-06 server wiring (Wave 3) — exposes tools via MCP stdio
- 11-HUMAN-UAT.md live tenant test (manual)

Plan 11-05 can now build its 5 tool handlers as 10-20-line wrappers around these 12 methods.

## Self-Check: PASSED

- Created file `packages/yigthinker-mcp-uipath/tests/test_client.py`: FOUND (575 lines)
- Modified file `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/client.py`: FOUND (402 lines)
- Commit `82af09f` (test(11-03)): FOUND
- Commit `a8ebe65` (feat(11-03)): FOUND
- `OrchestratorClient` importable: YES
- `RETRY_BACKOFFS == (1.0, 2.0, 4.0)`: YES
- `REQUEST_TIMEOUT_S == 30.0`: YES
- All 12 async methods present (grep verified): YES
- Constructor takes exactly 2 args (`auth`, `base_url`), no `http` kwarg: YES
- `X-UIPATH-OrganizationUnitId` header injection present in `_request`: YES
- `json.dumps(input_arguments or {})` in `start_job` (Finding 3 critical): YES
- `raise LookupError("No release found` / `No schedule found`: YES (both present)
- `GetQueueItemsByStatusCount(queueDefinitionId=` path literal: YES
- 19/19 client tests passing: YES
- 36/36 full-package tests passing: YES
