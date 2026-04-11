---
phase: 11-uipath-mcp-server
plan: 06
subsystem: uipath-mcp-package
tags: [mcp, stdio-server, lowlevel, uipath, wave-3]
wave: 3
requirements: [MCP-UI-01, MCP-UI-02]
one_liner: "Wire 5-tool TOOL_REGISTRY into an mcp.server.lowlevel.Server over stdio with UipathConfig.from_env (6 flat UIPATH_* vars) and a subprocess smoke test that proves list_tools returns all 5 ui_* tools via the real MCP SDK client"
dependency_graph:
  requires:
    - phase: 11-uipath-mcp-server
      provides: "Plan 11-02 UipathAuth (D-09 5-field sig), Plan 11-03 OrchestratorClient (D-13 2-arg sig), Plan 11-05 TOOL_REGISTRY (5 (InputModel, handler) tuples)"
  provides:
    - "build_server(config: UipathConfig) -> mcp.server.lowlevel.Server"
    - "UipathConfig dataclass (6 fields) + from_env classmethod reading UIPATH_CLIENT_ID/SECRET/BASE_URL/TENANT/ORGANIZATION/SCOPE"
    - "run_stdio() async entry wrapping stdio_server() + app.run()"
    - "__main__.main() CLI entry with asyncio.run + stderr logging + RuntimeError handling"
    - "tests/test_server_smoke.py stdio subprocess smoke test"
  affects:
    - "Plan 11-07 drift cleanup — MCP detection hint strings now align to shipped tool names (already fixed by 11-05's tool layer; 11-07 handles core yigthinker side)"
    - "Plan 11-08 README — documents the 6 UIPATH_* env vars and vault:// mapping that 11-06 ingests"
tech_stack:
  added: []
  patterns:
    - "mcp.server.lowlevel.Server with @app.list_tools() + @app.call_tool() decorators (NOT FastMCP per D-04)"
    - "Tool result serialization: single TextContent(type='text', text=json.dumps(result, default=str)) block per D-20 + RESEARCH Finding 6"
    - "Lazy OrchestratorClient construction inside _ensure_client closure — list_tools never creates httpx.AsyncClient"
    - "UipathConfig.from_env raises RuntimeError (not ValueError) listing ALL missing env vars in one message; UIPATH_SCOPE is optional with DEFAULT_SCOPE fallback"
    - "stdio smoke test subprocess pattern via mcp.ClientSession + mcp.client.stdio.stdio_client"
    - "ValidationError handling: pydantic errors surface as {'error': 'invalid_arguments', 'detail': exc.errors()} text blocks, never as raised exceptions"
    - "Belt-and-suspenders exception guard in call_tool (BLE001) — handlers already return dict per D-14, but a stray raise still produces a well-formed TextContent response so stdio never hangs"
key_files:
  created:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/config.py (UipathConfig dataclass + from_env + load_config wrapper + DEFAULT_SCOPE)"
    - "packages/yigthinker-mcp-uipath/tests/test_server_smoke.py (1 stdio subprocess test)"
  modified:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/server.py (NotImplementedError stub -> build_server + run_stdio + list_tools/call_tool handlers)"
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/__main__.py (raise-on-import stub -> asyncio.run(run_stdio()) CLI entry with KeyboardInterrupt/RuntimeError handling)"
    - "packages/yigthinker-mcp-uipath/tests/test_scaffold.py (test_main_entry_raises_until_06 -> test_server_exposes_build_server_after_06; asserts build_server(cfg) returns a Server instance)"
key_decisions:
  - "D-04 enforcement: imported Server from mcp.server.lowlevel only — zero FastMCP references in server.py (grep-verified in acceptance_criteria). The lowlevel API gives full control over TextContent serialization which is non-negotiable because core Yigthinker's _MCPToolWrapper joins TextContent.text blocks and has no handler for other content types."
  - "D-09 wiring verbatim: build_server passes scope=config.scope (singular string, not scopes=[...]) so UipathAuth receives the space-separated value RFC 6749 expects. The acceptance grep guards BOTH the presence of scope=config.scope AND the absence of scopes="
  - "D-13 wiring verbatim: OrchestratorClient(auth=auth, base_url=config.base_url) — exactly 2 kwargs, no http= passthrough. Client owns its httpx.AsyncClient internally per Plan 11-03."
  - "Lazy client construction pattern: _ensure_client closes over a state dict and creates OrchestratorClient only on the first call_tool. list_tools therefore never touches httpx, which matters because the smoke test deliberately provides dummy credentials — if the client were built eagerly the Orchestrator URL lookup could fire even for list_tools."
  - "UIPATH_SCOPE is OPTIONAL with DEFAULT_SCOPE fallback (5 scopes: OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring). The smoke test intentionally omits UIPATH_SCOPE from the subprocess env to exercise the fallback path on boot — if the scope name is ever accidentally renamed to UIPATH_SCOPES (plural), the smoke test breaks."
  - "call_tool belt-and-suspenders BLE001 except handler: handlers are spec'd (D-14) to return {'error': ...} dicts and never raise, but the lowlevel Server protocol mandates a valid response or the stdio client hangs indefinitely. The extra except wraps handlers in a safety net and logs via logger.exception so stderr carries the traceback while stdout stays protocol-clean."
  - "test_scaffold.test_main_entry_raises_until_06 had to be replaced: the original test imported server.main and asserted NotImplementedError, but Plan 11-06 moves main() to __main__.py and exposes build_server+run_stdio on server.py instead. Replaced with test_server_exposes_build_server_after_06 which constructs a real UipathConfig and asserts build_server returns a mcp.server.lowlevel.Server instance. Rule 3 deviation — the old test would have broken the suite; classified as a blocking issue caused by the current task."
requirements_completed: [MCP-UI-01, MCP-UI-02]
metrics:
  duration: ~2min
  tasks_completed: 2
  files_created: 2
  files_modified: 3
  tests_before: 46
  tests_after: 47
completed: 2026-04-11
---

# Phase 11 Plan 06: UiPath MCP Stdio Server Wiring Summary

**Wires the 5-entry TOOL_REGISTRY from Plan 11-05 into an `mcp.server.lowlevel.Server` exposed over stdio, with a subprocess smoke test that proves `python -m yigthinker_mcp_uipath` responds to `list_tools` with all 5 ui_* tools — making the package consumable by core Yigthinker's MCP loader.**

## Performance

- **Duration:** ~2 min (single session, no checkpoints, no tool calls wasted on dead ends because Plan 11-05 had already locked the real tool names)
- **Tasks:** 2/2 completed (both `type="auto"`)
- **Files created:** 2 (`config.py`, `test_server_smoke.py`)
- **Files modified:** 3 (`server.py`, `__main__.py`, `test_scaffold.py`)
- **Test delta:** 46 → 47 (added 1 smoke test; test_scaffold count unchanged, one assertion rewritten)

## Accomplishments

### Task 1 — config + server + CLI entry (commit `79960cb`)

- Created `yigthinker_mcp_uipath/config.py`:
  - `UipathConfig` frozen dataclass with the 6 locked fields (`client_id`, `client_secret`, `tenant_name`, `organization`, `scope`, `base_url`).
  - `from_env()` classmethod reads the 5 required vars + optional `UIPATH_SCOPE` (singular per D-10); raises `RuntimeError` listing ALL missing vars in one message.
  - `DEFAULT_SCOPE` module constant: `"OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring"` (RFC 6749 space-separated).
  - `load_config()` wrapper function added to satisfy the plan's `artifacts.contains = "load_config"` expectation.

- Wired `yigthinker_mcp_uipath/server.py`:
  - `build_server(config)` constructs `Server("yigthinker-mcp-uipath")` from `mcp.server.lowlevel`.
  - Creates `UipathAuth(client_id=..., client_secret=..., tenant_name=..., organization=..., scope=...)` per D-09 — grep-verified `scope=config.scope` (singular) present, `scopes=` absent.
  - Lazy `_ensure_client()` closure constructs `OrchestratorClient(auth=auth, base_url=config.base_url)` per D-13 — grep-verified `http=` absent.
  - `@app.list_tools()` iterates `TOOL_REGISTRY`, converting each `(InputModel, handler)` tuple into a `Tool(name, description, inputSchema)` using `input_model.model_json_schema()` and a fallback description of `(input_model.__doc__ or name).strip() or name`.
  - `@app.call_tool()` dispatches through `TOOL_REGISTRY.get(name)`, validates arguments via `input_model.model_validate`, invokes the handler with `(parsed, orch)`, and wraps the result as `[TextContent(type="text", text=json.dumps(result, default=str))]` per D-20 + Finding 6.
  - Unknown tool, validation error, and unhandled exception paths all return a single well-formed `TextContent` block (never raise to the stdio transport).
  - `run_stdio()` lazy-imports `mcp.server.stdio.stdio_server`, calls `UipathConfig.from_env()`, builds the app, and awaits `app.run(read_stream, write_stream, app.create_initialization_options())`.

- Wired `yigthinker_mcp_uipath/__main__.py`:
  - `main()` configures stderr logging (stdout stays clean for MCP protocol), then `asyncio.run(run_stdio())`.
  - Handles `KeyboardInterrupt` (exit 0) and `RuntimeError` (print to stderr + exit 1) so config-missing errors surface cleanly.

### Task 2 — stdio smoke test (commit `be746d2`)

- Created `tests/test_server_smoke.py` with one async test `test_server_smoke_list_tools_returns_5`:
  - Spawns `sys.executable -m yigthinker_mcp_uipath` via `StdioServerParameters` + `stdio_client` from `mcp.client.stdio`.
  - Passes the 5 required env vars as strings and **intentionally omits `UIPATH_SCOPE`** to exercise the `DEFAULT_SCOPE` fallback path on boot.
  - Opens a `ClientSession`, calls `session.initialize()` then `session.list_tools()`.
  - Asserts: exactly 5 tools, name set equals `{ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status}`, each tool has non-empty `description`, object-typed `inputSchema` dict, and `properties` key present.

## Verification

### Sanity command (11-06-01)

```
$ cd packages/yigthinker-mcp-uipath && python -c "from yigthinker_mcp_uipath.server import build_server; from yigthinker_mcp_uipath.tools import TOOL_REGISTRY; assert len(TOOL_REGISTRY) == 5; print('ok')"
ok
```

### Full Task 1 acceptance (server + config fields + D-15 AST walk)

```
$ python -c "from yigthinker_mcp_uipath.server import build_server; from yigthinker_mcp_uipath.config import UipathConfig; from yigthinker_mcp_uipath.tools import TOOL_REGISTRY; assert len(TOOL_REGISTRY) == 5; cfg_fields = {'client_id','client_secret','tenant_name','organization','scope','base_url'}; import dataclasses; actual = {f.name for f in dataclasses.fields(UipathConfig)}; assert actual == cfg_fields; print('ok')"
ok

$ python -c "import ast, pathlib; ...D-15 AST walk..."
ok
```

### Smoke test (11-06-02)

```
$ cd packages/yigthinker-mcp-uipath && python -m pytest tests/test_server_smoke.py -x -q
.                                                                        [100%]
1 passed in 0.84s
```

### Full package suite (plan-level gate)

```
$ cd packages/yigthinker-mcp-uipath && python -m pytest tests/ -x -q
...............................................                          [100%]
47 passed in 7.21s
```

All 46 pre-existing tests remained green after the scaffold test update, and the new smoke test brings the total to 47.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced `test_scaffold.test_main_entry_raises_until_06`**

- **Found during:** Task 1 — when the `from yigthinker_mcp_uipath.server import main` import in the old scaffold test started failing (Plan 11-06 wires `build_server` + `run_stdio` on `server.py` and moves `main()` to `__main__.py`, so `server.main` no longer exists).
- **Issue:** The Plan 11-01 scaffold test hard-asserted `with pytest.raises(NotImplementedError): server.main()` — that assertion is factually incompatible with the post-11-06 server module.
- **Fix:** Replaced the test body with `test_server_exposes_build_server_after_06` which imports `build_server` + `UipathConfig`, constructs a dummy config, and asserts `isinstance(build_server(cfg), mcp.server.lowlevel.Server)`. This turns the scaffold suite into a positive guard that the Plan 11-06 wiring survives future refactors.
- **Files modified:** `packages/yigthinker-mcp-uipath/tests/test_scaffold.py`
- **Commit:** `79960cb` (bundled with Task 1)
- **Rule:** Rule 3 (auto-fix blocking issues) — without this edit the plan-level verification `pytest tests/ -x -q` would have failed at the first file before reaching the smoke test.

### Intentional scope adjustments

- **`load_config()` wrapper:** The PLAN 11-06 `artifacts.contains` field specified `"load_config"` for `config.py`, while the action block only showed `UipathConfig.from_env`. Added a thin `load_config() -> UipathConfig` wrapper that delegates to `from_env()` so both the artifact contract and the ergonomic module-level entry point are satisfied. Not tracked as a deviation because it is additive and the plan listed it in `must_haves.artifacts.contains`.

## Self-Check

- [x] `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/config.py` exists
- [x] `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/server.py` exists and imports `Server` from `mcp.server.lowlevel`
- [x] `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/__main__.py` exists and calls `asyncio.run(run_stdio())`
- [x] `packages/yigthinker-mcp-uipath/tests/test_server_smoke.py` exists and passes
- [x] `UipathConfig` has exactly 6 fields mirroring the 6 env vars
- [x] `server.py` contains `tenant_name=config.tenant_name`, `organization=config.organization`, `scope=config.scope` (D-09 wiring)
- [x] `server.py` contains `OrchestratorClient(auth=auth, base_url=config.base_url)` and no `http=` (D-13 wiring)
- [x] `server.py` contains `TextContent(type="text"` and `json.dumps(result` (D-20 + Finding 6)
- [x] `server.py` has zero `FastMCP` references (D-04)
- [x] `server.py` has zero imports from core `yigthinker.*` (D-15) — AST-verified
- [x] Commit `79960cb` exists on master (feat task 1)
- [x] Commit `be746d2` exists on master (test task 2)
- [x] Full package suite (47 tests) green

## Self-Check: PASSED
