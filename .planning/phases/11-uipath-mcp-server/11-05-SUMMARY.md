---
phase: 11-uipath-mcp-server
plan: 05
subsystem: uipath-mcp-package
tags: [mcp-tools, handlers, tool-registry, uipath, pydantic, tdd, wave-2]
wave: 2
requirements: [MCP-UI-01]
one_liner: "5 UiPath MCP tool handlers (deploy/trigger/history/manage/queue) with Pydantic schemas + TOOL_REGISTRY, composing OrchestratorClient and build_nupkg into dict-returning async functions per D-14 (no raised exceptions)"
dependency_graph:
  requires:
    - phase: 11-uipath-mcp-server
      provides: "Plan 11-02 UipathAuth (D-09), Plan 11-03 OrchestratorClient (D-13 + 7 OData helpers), Plan 11-04 build_nupkg"
  provides:
    - "TOOL_REGISTRY: dict[str, (type[BaseModel], Callable[..., Awaitable[dict]])] — 5 entries"
    - "ui_deploy_process(workflow_name, script_path, folder_path, package_version) handler"
    - "ui_trigger_job(process_key, folder_path, input_arguments) handler"
    - "ui_job_history(process_key, folder_path, top) handler"
    - "ui_manage_trigger(process_key, action, folder_path, cron, trigger_name) handler"
    - "ui_queue_status(queue_name, folder_path) handler"
    - "10 respx-backed unit tests (happy + error path per tool) in tests/test_tools/"
  affects:
    - "Plan 11-06 server.py — iterates TOOL_REGISTRY to register MCP tools + dispatch call_tool"
tech_stack:
  added: []
  patterns:
    - "Pydantic BaseModel input schema per tool, field signatures verbatim from D-19"
    - "Literal[...] action dispatch for CRUD-style tools (ui_manage_trigger)"
    - "D-14 error-dict contract: all handlers return dicts, never raise to MCP protocol"
    - "Cross-field validation BEFORE any HTTP call (ui_manage_trigger missing_cron/missing_trigger_name guards)"
    - "Handler composes Plan 11-03 helpers (resolve_folder_id, get_release_key_by_process, get_schedule_id_by_name) rather than inlining OData queries"
    - "respx.mock at the httpx layer with monkeypatch of UipathAuth.auth_headers to skip OAuth2 in tests"
key_files:
  created:
    - "packages/yigthinker-mcp-uipath/tests/test_tools/__init__.py"
    - "packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_deploy_process.py (2 tests)"
    - "packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_trigger_job.py (2 tests)"
    - "packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_job_history.py (2 tests)"
    - "packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_manage_trigger.py (2 tests)"
    - "packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_queue_status.py (2 tests)"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_deploy_process.py"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_trigger_job.py"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_job_history.py"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_manage_trigger.py"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_queue_status.py"
  modified:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/__init__.py (empty stub -> populated TOOL_REGISTRY with 5 entries)"
    - "packages/yigthinker-mcp-uipath/tests/test_scaffold.py (test_tool_registry_empty -> test_tool_registry_populated, guards the new stable state)"
key_decisions:
  - "Plan test draft URL (UiPath.Server.Configuration.OData.StartJobs) discarded in favor of the ACTUAL URL in client.py (UiPath.Server.Jobs.StartJobs). Plan 11-03 is the contract owner; Plan 11-05 test mocks align to the real client implementation, not the plan's draft example."
  - "ui_job_history resolves process_key -> release_key FIRST before calling list_jobs, because client.list_jobs filters OData Jobs on Release/Key (not ReleaseName as the plan draft assumed). Graceful fallback: LookupError from missing release -> empty history ({count:0, jobs:[]}), NOT an error — a brand-new process with no jobs yet is a valid state, not a failure."
  - "ui_manage_trigger cross-field validation (missing_cron / missing_trigger_name) runs BEFORE resolve_folder_id so bad input short-circuits with zero HTTP traffic. Guarded by test_error_missing_cron_returns_dict asserting folders_route.call_count == 0."
  - "test_scaffold.test_tool_registry_empty was written for the Plan 11-01 empty-stub state and is factually incompatible with Plan 11-05's populated registry. Updated the test to test_tool_registry_populated (asserts the 5 expected keys + callable handlers). Rule 1/3 deviation — documented below."
  - "ui_queue_status catches ValueError (from client.get_queue_id 'queue not found' raise) rather than LookupError, matching the actual client.py contract. The plan's draft used LookupError which would have missed the real exception type."
requirements_completed: [MCP-UI-01]
duration: ~8min
completed: 2026-04-11
---

# Phase 11 Plan 05: UiPath MCP Tool Handlers Summary

**Five UiPath MCP tool handlers + Pydantic input schemas + populated TOOL_REGISTRY — all composing the Plan 11-02/11-03/11-04 contracts (UipathAuth D-09, OrchestratorClient D-13 + 7 OData helpers, build_nupkg) into dict-returning async functions with D-14 error-dict semantics so MCP stdio never sees a raised exception.**

## Performance

- **Duration:** ~8 min (single session, no checkpoints)
- **Tasks:** 2/2 completed (both TDD: Task 1 RED, Task 2 GREEN)
- **Files created:** 11 (5 tool handler modules, 5 test modules, 1 test package `__init__.py`)
- **Files modified:** 2 (`tools/__init__.py` populated, `test_scaffold.py` fixed)

## Accomplishments

### Task 1 — RED (commit `a655efb`)

Created `packages/yigthinker-mcp-uipath/tests/test_tools/` with 6 files (1 package init + 5 test modules = 10 test functions, one happy + one error path per tool).

| Tool | Happy path test | Error path test |
|------|-----------------|------------------|
| `ui_deploy_process` | Build + upload + release round-trip returns `{status: "deployed", process_key, release_key, folder_path, package_version}` | UploadPackage 500 returns `{error: "http_error", status: 500, detail}` (asyncio.sleep monkeypatched out for fast retry) |
| `ui_trigger_job` | StartJobs body body["startInfo"]["InputArguments"] is a JSON STRING (Finding 3 guard) + `{job_id, state: "Running", process_key}` | Empty folder list returns `{error: "folder_not_found", folder_path}` |
| `ui_job_history` | 2-job list shaped to `{process_key, count: 2, jobs: [...]}` with id/state/start_time/end_time/info per job | /odata/Jobs 400 returns `{error: "http_error", status: 400}` |
| `ui_manage_trigger` | `action="create"`, cron="0 9 * * *", trigger_name="morning" -> POST /odata/ProcessSchedules -> `{status: "created", schedule_id: 77, process_key, action: "create"}` | `action="create"`, cron=None -> `{error: "missing_cron", action: "create"}`, zero HTTP calls |
| `ui_queue_status` | QueueDefinitions + GetQueueItemsByStatusCount(queueDefinitionId=7,daysNo=7) -> `{queue_name, new:5, in_progress:2, failed:1, successful:42}` | Empty QueueDefinitions -> `{error: "queue_not_found", queue_name}` |

All 10 tests SHARE a `mock_auth` fixture that constructs UipathAuth with the D-09 5-field signature (`scope="OR.Execution ..."` as a single space-separated string) and monkeypatches `UipathAuth.auth_headers` to return a fake bearer — so tests never hit the real `/identity_/connect/token` endpoint.

Every OrchestratorClient is constructed via `OrchestratorClient(auth=..., base_url=BASE)` (D-13 locked 2-arg form). **Zero occurrences of `scopes=[...]` or `http=http` in `tests/test_tools/`** — the D-09 and D-13 guards pass.

**RED confirmed:** 5 `ModuleNotFoundError` collection errors (one per missing `yigthinker_mcp_uipath.tools.ui_*` module).

### Task 2 — GREEN (commit `8b1e09c`)

Replaced the empty-dict `tools/__init__.py` stub with 5 handler modules and a populated `TOOL_REGISTRY`.

**1. `tools/ui_deploy_process.py`** — composes `resolve_folder_id` + `build_nupkg` + `upload_package` + `create_release` into a single atomic deploy. Returns `{status: "deployed", process_key, release_key, folder_path, package_version}`. Catches `httpx.HTTPStatusError` -> `{error:"http_error"}`, `ValueError` (folder lookup) -> `{error:"folder_not_found"}`.

**2. `tools/ui_trigger_job.py`** — resolves folder, then calls `client.get_release_key_by_process` (Plan 11-03 helper), then `client.start_job(folder_id, release_key, input_arguments)`. The Plan 11-03 `start_job` handles the Finding 3 `json.dumps(input_arguments)` internally, so the handler passes the dict through unchanged. Returns `{job_id, state, process_key}`. Maps `LookupError` -> `release_not_found`, folder `ValueError` -> `folder_not_found`.

**3. `tools/ui_job_history.py`** — resolves folder, resolves release key, calls `client.list_jobs(folder_id, release_key, top)`. list_jobs returns a plain `list[dict]` (NOT a `{"value":[...]}` envelope as the plan draft assumed). Handler shapes each job into a compact summary dict `{id, state, start_time, end_time, info}`. On `LookupError` from release lookup, returns an empty history `{count:0, jobs:[]}` rather than an error — a brand-new process with no deployed release is a valid empty state.

**4. `tools/ui_manage_trigger.py`** — `Literal["create","pause","resume","delete"]` action dispatch. Cross-field validation fires BEFORE any HTTP call so bad input short-circuits loudly:
- `action="create"` + `cron is None` -> `{error:"missing_cron"}`
- `trigger_name is None` (any action) -> `{error:"missing_trigger_name"}`

`create` looks up release_key via Plan 11-03 helper then posts `/odata/ProcessSchedules`. `pause`/`resume` resolves `schedule_id_by_name` then PATCHes `Enabled` flag. `delete` resolves schedule_id then DELETEs. All four paths catch `LookupError` -> `trigger_not_found`, `ValueError` -> `folder_not_found`, `httpx.HTTPStatusError` -> `http_error`.

**5. `tools/ui_queue_status.py`** — resolves folder, `client.get_queue_id(folder_id, queue_name)`, `client.get_queue_status_count(folder_id, queue_id)`. The count endpoint is the modern `GetQueueItemsByStatusCount(queueDefinitionId=<id>,daysNo=7)` — **NOT** the legacy `GetQueueItemsCounts` typo (MEDIUM 2 guard). Maps Orchestrator's PascalCase `{New, InProgress, Failed, Successful}` to snake_case `{new, in_progress, failed, successful}`. Catches `ValueError` from `get_queue_id` -> `queue_not_found` (matching the actual client.py raise type, not the plan's draft `LookupError`).

**6. `tools/__init__.py`** — populated `TOOL_REGISTRY` dict mapping tool name -> `(InputModel, handler)` tuple for all 5 tools, plus the `Handler = Callable[[BaseModel, Any], Awaitable[dict]]` type alias Plan 11-06 will consume.

## Verification

```bash
cd packages/yigthinker-mcp-uipath && python -m pytest tests/test_tools/ -x -q
..........                                                               [100%]
10 passed in 1.91s

cd packages/yigthinker-mcp-uipath && python -m pytest tests/ -x -q
..............................................                          [100%]
46 passed in 6.43s
```

**Full package suite: 46/46 green** (36 baseline from Plans 11-01..11-04 + 10 new tool-handler tests).

### TOOL_REGISTRY contents (post-population)

```python
{
    "ui_deploy_process": (UiDeployProcessInput, _deploy),
    "ui_trigger_job":    (UiTriggerJobInput,    _trigger),
    "ui_job_history":    (UiJobHistoryInput,    _history),
    "ui_manage_trigger": (UiManageTriggerInput, _manage),
    "ui_queue_status":   (UiQueueStatusInput,   _queue),
}
```

Plan 11-06 will `from yigthinker_mcp_uipath.tools import TOOL_REGISTRY` and iterate it inside `list_tools` + `call_tool` dispatch. Handler tuple shape is frozen.

### Contract compliance guards (all green)

- `git diff packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/client.py` — empty (D-13 owner untouched)
- `git diff packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/auth.py` — empty (D-09 owner untouched)
- `git diff packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/nupkg.py` — empty (Plan 11-04 owner untouched)
- `grep -r "scopes=\[" packages/yigthinker-mcp-uipath/tests/test_tools/` -> 0 matches
- `grep -r "http=http" packages/yigthinker-mcp-uipath/tests/test_tools/` -> 0 matches
- `grep -r "GetQueueItemsCounts" packages/yigthinker-mcp-uipath/tests/test_tools/` -> only 1 docstring mention (explicitly labeled "NOT the legacy GetQueueItemsCounts typo")
- `grep "class UiDeployProcessInput" .../tools/ui_deploy_process.py` -> matches
- Every handler file contains `except httpx.HTTPStatusError` (D-14 error-handling guard)
- No handler file contains `raise httpx.HTTPStatusError` (handlers never re-raise)

## Deviations from Plan

### [Rule 3 - Blocking Issue] test_scaffold.test_tool_registry_empty became incompatible with populated registry

**Found during:** Task 2 verification (full package suite)
**Issue:** `tests/test_scaffold.py::test_tool_registry_empty` asserted `TOOL_REGISTRY == {}`. This was correct at Plan 11-01 when the registry was a stub, but Plan 11-05's entire purpose is to POPULATE the registry. Running `pytest tests/` after Task 2 produced 35 passed + 1 failed.
**Fix:** Renamed the test to `test_tool_registry_populated` and rewrote it to assert the registry contains exactly the 5 expected keys (ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status) and that each entry is a `(class, callable)` tuple. This turns the scaffold test into a stable long-lived contract guard rather than a one-phase transient.
**Files modified:** `packages/yigthinker-mcp-uipath/tests/test_scaffold.py`
**Commit:** `8b1e09c` (same commit as Task 2 since they're tightly coupled)
**Justification:** Rule 3 (blocking issue caused by current task changes). The test was designed to be replaced by Plan 11-05; the plan narrative even hinted at this but did not explicitly list it in `<files_modified>`. The new test is strictly stronger than the old one (asserts specific structure, not just emptiness).

### [Rule 3 - Plan Draft Drift] Plan test-code draft URLs did not match the actual client.py

**Found during:** Task 1 test writing
**Issue:** The 11-05-PLAN.md test example for `ui_trigger_job` mocks `/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs`, but the shipped `client.py` (Plan 11-03) uses `/odata/Jobs/UiPath.Server.Jobs.StartJobs`. Similarly the plan draft assumed `list_jobs` returns `{"value":[...]}` but the actual client returns `list[dict]`, and `get_queue_id` raises `ValueError` not `LookupError`.
**Fix:** Tests were written against the ACTUAL client.py contract (Plan 11-03 is the owner per D-13 lock), not the plan draft examples. Handlers were implemented to match: `ui_trigger_job` consumes `client.start_job` return shape (already-unwrapped first job dict), `ui_job_history` iterates `list_jobs` list directly, `ui_queue_status` catches `ValueError` for `queue_not_found`.
**Justification:** Rule 3 — the plan draft is advisory; the shipped module contracts are authoritative. Plan 11-03 locked its contracts with 19 passing tests before Plan 11-05 started; those tests codified the real shape.

### No auto-fixes to client.py / auth.py / nupkg.py

All three files were left **exactly** as Plans 11-02/11-03/11-04 shipped them. This was explicitly verified via empty `git diff` post-Task-2. The architect-not-executor invariant (D-01) and the plan-owner contracts (D-09, D-13) are preserved.

## Auth Gates

**None.** No interactive auth was needed — all tests use monkeypatched `UipathAuth.auth_headers` to return a fake bearer token. No UAT / human verification steps in this plan (those live in 11-HUMAN-UAT.md per the phase validation strategy).

## Known Stubs

**None in Plan 11-05 scope.** Every handler:
- Has real Pydantic input validation
- Composes real Plan 11-02/11-03/11-04 module calls
- Returns substantive dicts (no placeholder values, no "coming soon")
- Is wired into `TOOL_REGISTRY`

**Pending Plan 11-06 wiring** is NOT a stub — it's the next plan's scope. `TOOL_REGISTRY` is the contract handoff: 11-05 produces it, 11-06 consumes it into the MCP stdio server's `list_tools` + `call_tool` dispatch.

## Commits

| # | Hash      | Subject                                                          |
|---|-----------|------------------------------------------------------------------|
| 1 | `a655efb` | test(11-05): add failing tests for 5 UiPath tool handlers        |
| 2 | `8b1e09c` | feat(11-05): implement 5 UiPath tool handlers + tool registry    |

## Success Criteria (from 11-05-PLAN.md)

- [x] All 10 tests in `packages/yigthinker-mcp-uipath/tests/test_tools/` pass (10/10 green)
- [x] TOOL_REGISTRY has exactly 5 entries (ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status)
- [x] No handler raises `httpx.HTTPStatusError` out of its scope (D-14) — every handler has at least one `except httpx.HTTPStatusError` branch returning a dict
- [x] `ui_trigger_job` respects Finding 3 — the handler passes `input_arguments` dict to `client.start_job`, which internally calls `json.dumps`. Test assertion `isinstance(body["startInfo"]["InputArguments"], str)` is green.
- [x] Pydantic input schemas match D-19 field signatures verbatim
- [x] No test fixture uses `scopes=[...]` (D-09 compliance) — grep-verified
- [x] No test fixture passes `http=<AsyncClient>` to OrchestratorClient (D-13 compliance) — grep-verified
- [x] `test_ui_queue_status.py` mocks `GetQueueItemsByStatusCount` (NOT `GetQueueItemsCounts`)
- [x] `client.py`, `auth.py`, and `nupkg.py` were not modified by this plan (empty git diff)
- [x] MCP-UI-01 partially satisfied: 5 tool handler functions exist and are callable
- [x] Plan 11-06 can `from yigthinker_mcp_uipath.tools import TOOL_REGISTRY` and wire it to the MCP Server without any additional work in 11-05's scope

## Self-Check: PASSED

- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_deploy_process.py` — FOUND
- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_trigger_job.py` — FOUND
- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_job_history.py` — FOUND
- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_manage_trigger.py` — FOUND
- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/ui_queue_status.py` — FOUND
- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/tools/__init__.py` — FOUND (populated)
- `packages/yigthinker-mcp-uipath/tests/test_tools/__init__.py` — FOUND
- `packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_deploy_process.py` — FOUND
- `packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_trigger_job.py` — FOUND
- `packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_job_history.py` — FOUND
- `packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_manage_trigger.py` — FOUND
- `packages/yigthinker-mcp-uipath/tests/test_tools/test_ui_queue_status.py` — FOUND
- Commit `a655efb` (test RED) — FOUND in git log
- Commit `8b1e09c` (feat GREEN) — FOUND in git log
- Full package pytest — 46/46 PASSED (36 baseline + 10 new)
- Full tool-only pytest — 10/10 PASSED
- client.py / auth.py / nupkg.py unchanged — VERIFIED via empty git diff
