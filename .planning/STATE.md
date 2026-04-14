---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Workflow & RPA Bridge
status: Phase complete — ready for verification
stopped_at: Completed 12-08-PLAN.md
last_updated: "2026-04-12T09:58:55.112Z"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 26
  completed_plans: 26
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** A user can interact via CLI REPL, IM channels, or TUI connected to the Gateway, having AI-assisted data analysis conversations with tool calls -- same agent, multiple surfaces. Repeatable analysis patterns become automated workflows deployed to RPA platforms.
**Current focus:** Phase 12 — power-automate-mcp-server

## Current Position

Phase: 12 (power-automate-mcp-server) — EXECUTING
Plan: 8 of 8

## Performance Metrics

**Velocity (from v1.0):**

- Total plans completed: 18
- Average duration: 4.2 minutes
- Total execution time: ~75 minutes

**By Phase (v1.0):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | 13min | 3.3min |
| 02 | 2 | 7min | 3.5min |
| 03 | 2 | 18min | 9.0min |
| 04 | 3 | 15min | 5.0min |
| 05 | 2 | 6min | 3.0min |
| 07 | 5 | 18min | 3.6min |
| Phase 08 P01 | 3min | 2 tasks | 4 files |
| Phase 08 P02 | 4min | 1 tasks | 9 files |
| Phase 08 P03 | 4min | 2 tasks | 4 files |
| Phase 09-deployment-lifecycle P01 | 90min | 3 tasks | 11 files |
| Phase 09-deployment-lifecycle P03 | ~6 min | 3 tasks | 4 files |
| Phase 09 P02 | 35 | 3 tasks | 13 files |
| Phase 10 P03 | 7min | 7 tasks | 8 files |
| Phase 10-gateway-rpa-behavior P01 | 60min | 6 tasks | 14 files |
| Phase 10-gateway-rpa-behavior P02 | 6min | 4 tasks | 3 files |
| Phase 10-gateway-rpa-behavior P04 | 15min | 6 tasks | 7 files |
| Phase 11-uipath-mcp-server P01 | 4min | 2 tasks | 12 files |
| Phase 11-uipath-mcp-server P02 | 15min | 2 tasks | 2 files |
| Phase 11-uipath-mcp-server P04 | ~2.5min | 2 tasks | 2 files |
| Phase 11-uipath-mcp-server P03 | ~10min | 2 tasks | 2 files |
| Phase 11-uipath-mcp-server P05 | ~8min | 2 tasks | 13 files |
| Phase 11-uipath-mcp-server P06 | ~2min | 2 tasks | 5 files |
| Phase 11-uipath-mcp-server P07 | ~6min | 2 tasks | 5 files |
| Phase 11-uipath-mcp-server P08 | ~6min | 1 task tasks | 1 file files |
| Phase 12 P01 | 3min | 2 tasks | 18 files |
| Phase 12 P04 | 2min | 2 tasks | 2 files |
| Phase 12 P03 | 3min | 2 tasks | 2 files |
| Phase 12 P02 | 4min | 2 tasks | 2 files |
| Phase 12 P05 | 3min | 2 tasks | 12 files |
| Phase 12 P07 | 3min | 2 tasks | 5 files |
| Phase 12 P06 | 4min | 2 tasks | 4 files |
| Phase 12 P08 | 2min | 1 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v1.0 complete: AgentLoop, Gateway, TUI, Streaming, Teams, Memory, Spawn Agent all validated
- Dashboard permanently removed -- headless product by design
- Yigthinker is the architect, not the executor -- generates automation, doesn't run it
- Scripts must be self-contained -- Gateway unavailability only disables self-healing
- 3 deploy modes: auto (API), guided (paste-ready), local (OS scheduler)
- MCP server packages are independent repos, not bundled
- [Phase 08]: Merge-based save_index: read-inside-lock + dict.update to prevent concurrent write loss
- [Phase 08]: Sequential version numbering (v1, v2, v3) per D-05
- [Phase 08]: Global registry at ~/.yigthinker/workflows/registry.json per D-07
- [Phase 08]: Removed import sys from base template -- unused and triggers AST validation blocker
- [Phase 08]: Step params serialized via |tojson filter to prevent SSTI in rendered scripts
- [Phase 08]: from_history uses tool_use_id matching to pair tool_use with tool_result for error detection
- [Phase 08]: Feature gate + ModuleNotFoundError guard double-protection for optional tool groups
- [Phase 09-deployment-lifecycle]: save_index switched to per-entry merge so Phase 9 patches preserve Phase 8 fields (latest_version, created_at)
- [Phase 09-deployment-lifecycle]: Dual python_exe context (python_exe_windows + python_exe_posix) so crontab never leaks Windows backslashes (Pitfall 7)
- [Phase 09-deployment-lifecycle]: Lazy-default-on-read upgrade pattern: _fill_*_defaults() helpers + per-entry merge save, no disk migration needed for Phase 8→Phase 9 schema bump (D-13)
- [Phase 09-deployment-lifecycle]: Rolling back to the currently-active version returns is_error=True (not no-op) for loud-failure safety
- [Phase 09-deployment-lifecycle]: workflow_manage pause/resume/rollback return instructional next_step dicts keyed by deploy target; tool is architect-not-executor per D-02/D-15
- [Phase 09-deployment-lifecycle]: health_check excludes retired workflows from rows but includes paused workflows with overdue=False (D-16 + plan review note #2)
- [Phase 09]: Guided mode builds bundles at runtime via TemplateEngine.render_text + zipfile — no pre-canned artifacts shipped
- [Phase 09]: Auto mode uses importlib.util.find_spec to inspect MCP package availability — never imports the module (architect-not-executor invariant)
- [Phase 09]: cron_to_pa_recurrence supports 4 canonical shapes (daily/weekly/monthly/every-N-hours); irregular crons fall back to Day/1 with needs_manual_review=True
- [Phase 10]: [Phase 10-03]: PatternStore _save_locked helper prevents FileLock reentrancy deadlock in suppress() (Pitfall 5)
- [Phase 10]: [Phase 10-03]: CORR-04a lazy suppression pruning happens inside list_active under the existing lock — no background sweeper
- [Phase 10]: [Phase 10-03]: suggest_automation can_deploy_to via importlib.util.find_spec only — never imports MCP packages
- [Phase 10-gateway-rpa-behavior]: CORR-03: RPAStateStore uses sync-blocking sqlite3 (not aiosqlite), clone of EventDeduplicator pattern; grep-verified zero occurrences of asyncio.to_thread/aiosqlite/async def
- [Phase 10-gateway-rpa-behavior]: Lazy controller wiring: GatewayServer routes read self._rpa_controller at request time via closure; start() builds the controller AFTER build_app() resolves the LLM provider, returning 503 while still None
- [Phase 10-gateway-rpa-behavior]: Stubbed extraction at _extract_decision_stub (exact name) — dedup + circuit breaker + counters fully work without LLM; Plan 10-02 replaces method by name
- [Phase 10-gateway-rpa-behavior]: CORR-01 template rewrite: checkpoint_utils.py.j2 POSTs to /api/rpa/callback with D-08 shape (fresh uuid4/attempt, Bearer auth via config.gateway_token) and /api/rpa/report with D-09 shape (run_id/started_at/finished_at); GW-RPA-05 ConnectionError fallback preserved
- [Phase 10-gateway-rpa-behavior]: Plan 10-02: parse_extraction_response is sync — no await path, CORR-04b layered fallback (direct → strip fences → regex) all routes converge to extraction_failed escalate dict
- [Phase 10-gateway-rpa-behavior]: Plan 10-02: extraction LLM user message excludes workflow_name / callback_id / version (routing keys, not classification signals); traceback truncated to 2000 chars pre-serialization to fit D-05's ~500-token budget
- [Phase 10-gateway-rpa-behavior]: Plan 10-02: fix_applied action without a valid integer retry_delay_s escalates with extraction_failed — refuses to retry blindly when LLM violates schema
- [Phase 10-gateway-rpa-behavior]: BHV-02 uses startup alert provider callback (CORR-02), not SessionStart hook — HookResult has no context-injection variant
- [Phase 10-gateway-rpa-behavior]: BHV-05 CANDIDATE_PATTERNS extension appended at call site (CORR-04c), DREAM_PROMPT constant preserved byte-identical for Phase 5 regression safety
- [Phase 10-gateway-rpa-behavior]: Pitfall 3 double-defense: startup alert provider wrapped in try/except at both closure definition and AgentLoop.run call site
- [Phase 10-gateway-rpa-behavior]: AutoDream pattern_store is optional kwarg (default None) to avoid breaking existing tests; disabled stores silently discard parsed patterns
- [Phase 11-uipath-mcp-server]: Plan 11-01 scaffold ships 9 module stubs + 3 test files; server.main() raises NotImplementedError with active test guard until Plan 11-06 replaces it
- [Phase 11-uipath-mcp-server]: conftest.py exposes sample_uipath_env with UIPATH_SCOPE singular key per D-10 (flat underscore keys, NOT slash-separated)
- [Phase 11-uipath-mcp-server]: config.py stub deferred to Plan 11-06 alongside server wiring (plan file is authoritative over VALIDATION.md Wave 0 list for file scope)
- [Phase 11-uipath-mcp-server]: Plan 11-02 locks UipathAuth(client_id, client_secret, tenant_name, organization, scope: str) per D-09; scope is a single space-separated str (RFC 6749), never a list — grep-guarded by test_form_body_uses_space_separated_scope
- [Phase 11-uipath-mcp-server]: Plan 11-02 asyncio.Lock uses field(default_factory=asyncio.Lock), NOT default=asyncio.Lock() — latter would share one lock across instances; Pitfall 4 thundering-herd guarded by test_concurrent_get_token_one_request
- [Phase 11-uipath-mcp-server]: Plan 11-02 exports TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token" and SAFETY_MARGIN_S = 60 at module level for Plan 11-03 OrchestratorClient consumption
- [Phase 11-uipath-mcp-server]: Plan 11-02 uses time.monotonic() (monkeypatchable via yigthinker_mcp_uipath.auth.time.monotonic) — not time.time() — so expiry tests can advance a fake clock without wall-time drift
- [Phase 11-uipath-mcp-server]: Plan 11-04 build_nupkg is a pure function (no output disk I/O) using stdlib zipfile + ZIP_DEFLATED; 4 verbatim templates from UiPath cli_pack.py; operate.json (NOT project.json — D-16 correction per RESEARCH.md Finding 4); Pitfall 6 guard asserted at test layer
- [Phase 11-uipath-mcp-server]: Plan 11-03 OrchestratorClient constructor locked at `(auth: UipathAuth, base_url: str)` per D-13 — exactly 2 args, httpx.AsyncClient created internally in __init__, no `http` kwarg; Plan 11-05 handler tests MUST match this shape
- [Phase 11-uipath-mcp-server]: Plan 11-03 retry loop uses `enumerate(RETRY_BACKOFFS)` with explicit `is_last_attempt` check to avoid double-counting; 5xx and httpx.NetworkError retry, 4xx fails immediately via raise_for_status (D-13)
- [Phase 11-uipath-mcp-server]: Plan 11-03 RESEARCH.md Open Question 3 disposition — `resolve_folder_id` does NOT inject X-UIPATH-OrganizationUnitId (Folders is organization-scoped); all other folder-scoped helpers including the two new lookup helpers (`get_release_key_by_process`, `get_schedule_id_by_name`) DO inject the header
- [Phase 11-uipath-mcp-server]: Plan 11-03 `start_job` serializes InputArguments as `json.dumps(input_arguments or {})` (JSON STRING inside `startInfo`) per RESEARCH.md Finding 3 critical note — UiPath rejects StartJobs with nested-object InputArguments; guarded by `test_start_job_serializes_input_arguments_as_json_string`
- [Phase 11-uipath-mcp-server]: Plan 11-05 TOOL_REGISTRY populated with 5 (InputModel, handler) tuples — stable contract handoff for Plan 11-06 MCP server wiring
- [Phase 11-uipath-mcp-server]: Plan 11-05 handlers align to ACTUAL client.py contract (Plan 11-03 owner) not plan draft examples — UiPath.Server.Jobs.StartJobs URL, list_jobs returning list[dict] not value-envelope, get_queue_id raises ValueError not LookupError
- [Phase 11-uipath-mcp-server]: Plan 11-05 ui_manage_trigger cross-field validation (missing_cron/missing_trigger_name) fires BEFORE resolve_folder_id — bad input short-circuits with zero HTTP; test guards with folders_route.call_count == 0
- [Phase 11-uipath-mcp-server]: Plan 11-05 scaffold test updated: test_tool_registry_empty -> test_tool_registry_populated (asserts 5 expected keys + callable handlers) — Rule 3 deviation, necessary to unblock full suite after populating the registry that was intentionally empty in Plan 11-01
- [Phase 11-uipath-mcp-server]: Plan 11-06 wires mcp.server.lowlevel.Server (NOT FastMCP per D-04) with @app.list_tools() + @app.call_tool() decorators iterating TOOL_REGISTRY; tool results serialized as single TextContent(type='text', text=json.dumps(result, default=str)) per D-20 + Finding 6
- [Phase 11-uipath-mcp-server]: Plan 11-06 UipathConfig dataclass has 6 fields (client_id, client_secret, tenant_name, organization, scope, base_url); from_env raises RuntimeError listing ALL missing required vars; UIPATH_SCOPE is optional with DEFAULT_SCOPE fallback — smoke test intentionally omits it to exercise the fallback path
- [Phase 11-uipath-mcp-server]: Plan 11-06 lazy OrchestratorClient construction via _ensure_client closure — list_tools never creates httpx.AsyncClient so smoke tests with dummy creds don't leak network attempts
- [Phase 11-uipath-mcp-server]: Plan 11-06 test_scaffold.test_main_entry_raises_until_06 replaced with test_server_exposes_build_server_after_06 — Rule 3 deviation: old test asserted server.main raised NotImplementedError, but Plan 11-06 moved main() to __main__.py and exposes build_server+run_stdio on server.py instead
- [Phase 11-uipath-mcp-server]: Plan 11-07 D-05 drift cleanup complete: 6 literal edits across mcp_detection.py, workflow_manage.py, test_workflow_deploy.py — all three canonical strings (yigthinker_mcp_uipath / ui_deploy_process / yigthinker[rpa-uipath]) now match the shipped package
- [Phase 11-uipath-mcp-server]: Plan 11-07 added rpa-uipath optional extra to core pyproject.toml pointing at yigthinker-mcp-uipath distribution — enables `pip install yigthinker[rpa-uipath]` once both packages are published
- [Phase 11-uipath-mcp-server]: Plan 11-07 drift-guard test (tests/test_tools/test_mcp_detection.py) uses regex-only scan of yigthinker/tools/workflow/ — never imports yigthinker_mcp_uipath (D-15 architect-not-executor invariant preserved)
- [Phase 11-uipath-mcp-server]: Plan 11-07 D-07 pin test relaxed from `canonical_hits == 1` to `>= 1` (Rule 3 deviation): suggest_automation.py has 2 canonical references (module docstring + find_spec call), both legitimate; exact find_spec call shape still asserted to hold the invariant
- [Phase 11-uipath-mcp-server]: Plan 11-08 README uses UIPATH_SCOPE singular exclusively — the 'singular-not-plural' explanatory sentence was rewritten so the forbidden plural literal never appears in the file, satisfying VALIDATION Row 11-08-01 grep guard
- [Phase 11-uipath-mcp-server]: Plan 11-08 README vault mapping section documents the exact _resolve_env transform (strip vault://, uppercase remainder) and explicitly warns against slash-style keys per D-10 — flat underscore is the only supported form
- [Phase 11-uipath-mcp-server]: Plan 11-08 legacy identifier 'yigthinker_uipath_mcp' rewritten out of troubleshooting text — drift guards treat its presence as a regression regardless of context, so counter-examples must also omit the literal string
- [Phase 12]: Cloned Phase 11 package structure exactly per D-02; msal added as fourth dep per D-15; POWERAUTOMATE_ env prefix per D-11
- [Phase 12]: Flow builder uses fixed dict template embedded in function (D-20), paralleling Phase 11 nupkg.py pattern
- [Phase 12]: Auth mocked at get_token level (D-26) -- MSAL never involved in client tests
- [Phase 12]: MSAL app created via @cached_property on _app -- lazy init avoids network at import; tests inject mocks via instance __dict__ for cached_property
- [Phase 12]: Tool handler tests use AsyncMock for client instead of respx (handler layer tests shape, not HTTP)
- [Phase 12]: Extended existing test_mcp_detection.py with PA assertions rather than creating new file (D-29)
- [Phase 12]: Plan 12-06 wires mcp.server.lowlevel.Server with TOOL_REGISTRY dispatch; config.py reads 6 env vars (3 required, 3 optional); lazy client construction via _ensure_client closure
- [Phase 12]: README documents PowerAutomate.Flows.Read/Write permissions (corrected from D-30 per RESEARCH.md Finding 5)

### Pending Todos

- Align README and packaging guidance with v1.0 completion
- Decide whether the new `test` extra should become the default contributor setup path

### Blockers/Concerns

- Windows constraint: uvloop unavailable (gateway token file protection resolved via icacls)
- MCP server packages (PA, UiPath) are new repos -- need separate pyproject.toml and CI
- Phase 11 needs research: UiPath .nupkg Python Activity schema
- Phase 12 needs research: PA Dataverse clientdata payload, Azure Function deployment

## Session Continuity

Last session: 2026-04-14T14:45:32Z
Stopped at: Completed quick-260414-mu3
Resume file: None
