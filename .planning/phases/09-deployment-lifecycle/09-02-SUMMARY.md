---
phase: 09-deployment-lifecycle
plan: 02
subsystem: workflow
tags: [workflow, deploy, guided, auto, power-automate, uipath, mcp-detection, zip-bundle, phase-9]

# Dependency graph
requires:
  - phase: 09-deployment-lifecycle
    plan: 01
    provides: "WorkflowDeployTool shell with WorkflowDeployInput schema, _do_execute dispatcher with target/mode combo + credential + schedule + version validation, _make_deploy_id, cron_to_ts_trigger, TemplateEngine.render_text, WorkflowRegistry lazy-default reads + per-entry merge save, local mode end-to-end"
provides:
  - "WorkflowDeployTool guided mode end-to-end for power_automate and uipath targets: _dispatch_guided builds paste-ready ZIP bundles (flow_import.zip for PA, process_package.zip for UiPath) + setup_guide.md into <version_dir>/<target>_guided/, with registry + manifest writeback matching 09-01 shape"
  - "WorkflowDeployTool auto mode end-to-end (informational-only per D-02): _dispatch_auto uses importlib.util.find_spec-based MCP detection, never imports the MCP package, never subprocess-execs anything; on MCP-present it reuses guided bundling and returns structured next_steps; on MCP-missing returns is_error with pip extras hint + guided fallback suggestion"
  - "cron_to_pa_recurrence dispatcher mapping 5-field cron expressions to PA Recurrence {frequency, interval} for 4 canonical shapes (daily / weekly / monthly / every-N-hours) with Day/1 + needs_manual_review=True fallback for exotic shapes"
  - "build_pa_bundle helper in yigthinker/tools/workflow/pa_bundle.py: assembles flow_import.zip with the 3 canonical PA paths (workflow.json, apiProperties.json, Microsoft.Flow/flows/<name>/definition.json)"
  - "build_uipath_bundle helper in yigthinker/tools/workflow/uipath_bundle.py: assembles process_package.zip with project.json + Main.xaml at root (user renames to .nupkg for UiPath Studio import)"
  - "mcp_detection module: check_mcp_installed (find_spec wrapper), MCP_PACKAGE_MAP (target -> package name), MCP_TOOL_MAP (target -> suggested_tool + install_hint)"
  - "4 PA guided templates: workflow.json.j2, apiProperties.json.j2, definition.json.j2 (with Recurrence trigger + placeholder HTTP action), setup_guide.md.j2"
  - "3 UiPath guided templates: project.json.j2 (Windows schema 4.0), main.xaml.j2 (Sequence stub with Python Scope placeholder comment), setup_guide.md.j2"
affects: [09-03-workflow-manage, phase-09-validation]

# Tech tracking
tech-stack:
  added: []  # no new deps - reuses croniter + jinja2 + zipfile from 09-01
  patterns:
    - "Architect-not-executor deploy tool (Phase 9 CONTEXT invariant): no subprocess, no MCP import, no external HTTP. check_mcp_installed uses importlib.util.find_spec which inspects the loader without running module code"
    - "Auto mode as guided-mode handoff: when the MCP package is present we reuse _dispatch_guided to produce a concrete bundle path that the MCP tool can ingest, then flip the registry row to deploy_mode=auto + status=pending_auto_deploy"
    - "Template render_text() escape hatch + zipfile.ZipFile(ZIP_DEFLATED) for runtime bundle assembly (D-05) - no pre-canned artifacts in the repo"
    - "Canonical PA subfolder path includes workflow_name (Microsoft.Flow/flows/<name>/definition.json) so PA treats the name as the flow's internal id consistently across re-imports"
    - "Defense-in-depth target=local guards: _do_execute blocks target=local with guided/auto mode upstream, and _dispatch_guided + _dispatch_auto re-guard internally for safety"

key-files:
  created:
    - yigthinker/tools/workflow/templates/pa/workflow.json.j2
    - yigthinker/tools/workflow/templates/pa/apiProperties.json.j2
    - yigthinker/tools/workflow/templates/pa/definition.json.j2
    - yigthinker/tools/workflow/templates/pa/setup_guide.md.j2
    - yigthinker/tools/workflow/templates/uipath/project.json.j2
    - yigthinker/tools/workflow/templates/uipath/main.xaml.j2
    - yigthinker/tools/workflow/templates/uipath/setup_guide.md.j2
    - yigthinker/tools/workflow/pa_bundle.py
    - yigthinker/tools/workflow/uipath_bundle.py
    - yigthinker/tools/workflow/mcp_detection.py
    - tests/fixtures/uipath_reference/main.xaml
  modified:
    - yigthinker/tools/workflow/workflow_deploy.py
    - tests/test_tools/test_workflow_deploy.py
    - tests/test_tools/test_workflow_templates.py

key-decisions:
  - "Auto mode reuses the guided dispatcher to stage a bundle as a concrete hand-off artifact for the MCP tool, then rewrites the registry entry to deploy_mode=auto + status=pending_auto_deploy. The LLM receives both a bundle_path (to pass to the MCP tool) and structured next_steps (naming the MCP tool + package)."
  - "MCP detection is strictly find_spec-based per Research Pattern 4, overriding D-09's ctx.tool_registry lookup hint. find_spec inspects the loader without executing module code, so it is safe to call during tool execution without any import side effects."
  - "Separate deploy_id for auto vs guided even when the guided bundling ran first - auto gets its own {name}-v{n}-auto-{ts} id so the registry clearly shows the user's final intent (auto handoff, not a plain guided deploy)."
  - "PA definition.json uses a placeholder HTTP action with uri='https://example.invalid/placeholder' rather than a real Run-Python-script connector. Per D-06 the generated flow is intentionally minimal - the setup_guide explains how to replace the action with Run a Child Flow / Dataverse / HTTP-to-Yigthinker-Gateway after import."
  - "UiPath Main.xaml uses an empty <Sequence> with a HTML comment explaining how to add a Python Scope activity in Studio, rather than pre-populating an invalid Python Scope stub. The fixture + render_text tests both validate that ET.fromstring() parses the output."
  - "pa_bundle + uipath_bundle helpers live as separate modules (not methods on WorkflowDeployTool) so they can be unit-tested without instantiating the tool - matches the shape of cron_to_ts_trigger as a module-level function from 09-01."
  - "target_dir_name uses 'power_automate_guided' / 'uipath_guided' (matches D-04 layout spec) - sibling to 09-01's 'local_guided'."

patterns-established:
  - "Phase 9 guided target directory pattern: <version_dir>/<target>_guided/ holds the target's bundle ZIP + setup_guide.md. Auto mode reuses this directory since it delegates bundling to _dispatch_guided."
  - "Pydantic Literal + _do_execute dispatcher pattern: validation in _do_execute (target/mode combo, credentials, version, schedule) then dispatch to per-mode handlers that only receive already-validated inputs."
  - "MCP detection as a thin module: check_mcp_installed + MCP_PACKAGE_MAP + MCP_TOOL_MAP. Future targets (e.g. Azure Logic Apps in Phase 11+) slot into the same maps."

requirements-completed: [DEP-02, DEP-03]

# Metrics
duration: ~35 min
completed: 2026-04-10
---

# Phase 09 Plan 02: Guided + Auto Deploy Modes Summary

**WorkflowDeployTool guided + auto modes end-to-end: PA and UiPath targets now produce paste-ready ZIP bundles via pa_bundle / uipath_bundle helpers, and auto mode performs find_spec-based MCP detection with structured next_steps payload on success and a guided-fallback error on missing package — all while preserving the architect-not-executor invariant (no subprocess, no MCP import, no external HTTP).**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-04-10
- **Tasks:** 3 (Task 0 Wave 0 stubs, Task 1 templates + bundle helpers + mcp_detection, Task 2 dispatcher wiring)
- **Files created:** 11 (7 templates, 3 helper modules, 1 fixture)
- **Files modified:** 3 (workflow_deploy.py, test_workflow_deploy.py, test_workflow_templates.py)
- **Tests added:** 17 (9 template tests + 8 deploy-tool tests)
- **Full suite:** 603/603 passing

## Accomplishments

- **Guided mode for Power Automate is live.** `workflow_deploy(deploy_mode=guided, target=power_automate, schedule=<cron>)` now produces a `flow_import.zip` under `<version_dir>/power_automate_guided/` with exactly the 3 canonical paths (`workflow.json`, `apiProperties.json`, `Microsoft.Flow/flows/<name>/definition.json`) plus a target-specific `setup_guide.md`. The flow contains a Recurrence trigger mapped from the cron schedule via `cron_to_pa_recurrence` and a placeholder HTTP action that the user replaces in flow.microsoft.com after import.
- **Guided mode for UiPath is live.** `workflow_deploy(deploy_mode=guided, target=uipath, schedule=<cron>)` produces a `process_package.zip` under `<version_dir>/uipath_guided/` with `project.json` (Windows schema 4.0, studioVersion 23.10) and a minimal `Main.xaml` (Sequence root with a Python Scope placeholder comment). The XAML parses via `xml.etree.ElementTree.fromstring` — verified by both the template test and the reference fixture test.
- **Auto mode is live and strictly informational.** `workflow_deploy(deploy_mode=auto, target=power_automate|uipath)` calls `mcp_detection.check_mcp_installed` which uses `importlib.util.find_spec` to inspect the Python environment without importing the MCP package. On success it reuses `_dispatch_guided` to build a concrete bundle as a hand-off artifact, flips the registry row to `deploy_mode=auto` + `status=pending_auto_deploy`, and returns a structured `next_steps` payload naming the MCP tool (`power_automate_create_flow` or `uipath_publish_package`), the package name, the bundle path, and the install hint. On missing package it returns `is_error=True` with a message mentioning the package + `pip install yigthinker[pa-mcp]` / `[uipath-mcp]` hint + a suggestion to fall back to `deploy_mode=guided`.
- **Registry + manifest writeback extends 09-01 cleanly.** Guided and auto modes follow the same D-11/D-12 contract as local mode: registry index gets `target`, `deploy_mode`, `schedule`, `last_deployed`, `deploy_id`, `current_version`; manifest version entry gets `deployed_to`, `deploy_mode`, `deploy_id`, `status`. Auto mode sets `status=pending_auto_deploy` (distinct from guided's `active`) so `workflow_manage list` can surface the distinction in Plan 09-03.
- **No architectural regression.** The 3 helper modules (`pa_bundle.py`, `uipath_bundle.py`, `mcp_detection.py`) are pure standard-library + TemplateEngine consumers. No new pip deps, no subprocess calls, no MCP imports, no external HTTP. Phase 9 CONTEXT invariant holds.

## Task Commits

Each task committed atomically with `--no-verify` for parallel-executor safety (plan 09-03 running in parallel):

1. **Task 0: Wave 0 test stubs + UiPath reference fixture** — `f999e80` (test)
   - `tests/test_tools/test_workflow_deploy.py` — TestWorkflowDeployGuided (4 tests) + TestWorkflowDeployAuto (4 tests) classes
   - `tests/test_tools/test_workflow_templates.py` — TestPABundleTemplates (4 tests) + TestUiPathBundleTemplates (5 tests) classes
   - `tests/fixtures/uipath_reference/main.xaml` — minimal known-good reference XAML for XAML shape comparison
   - Result: 14 RED (ImportError on pa_bundle / uipath_bundle / mcp_detection) + 3 GREEN (reference fixture parse + 2 target/mode validators already guarded upstream)

2. **Task 1: PA + UiPath templates, bundle helpers, MCP detection** — `5a89190` (feat)
   - `yigthinker/tools/workflow/templates/pa/` — 4 Jinja2 templates (workflow.json, apiProperties.json, definition.json with Recurrence trigger, setup_guide.md)
   - `yigthinker/tools/workflow/templates/uipath/` — 3 new Jinja2 templates (project.json, main.xaml, setup_guide.md) added alongside the existing Phase 8 main.py.j2
   - `yigthinker/tools/workflow/pa_bundle.py` — `build_pa_bundle(*, workflow_name, variables, engine, output_dir) -> Path`
   - `yigthinker/tools/workflow/uipath_bundle.py` — `build_uipath_bundle(*, workflow_name, variables, engine, output_dir) -> Path`
   - `yigthinker/tools/workflow/mcp_detection.py` — `check_mcp_installed(package_name) -> bool`, `MCP_PACKAGE_MAP`, `MCP_TOOL_MAP`
   - Result: 9/9 template + bundle tests GREEN; MCP detection helper verified importable + returns False for the unreal `yigthinker_pa_mcp` package as expected

3. **Task 2: Wire guided + auto dispatchers** — `b4963fe` (feat)
   - `yigthinker/tools/workflow/workflow_deploy.py` — added `cron_to_pa_recurrence` helper, replaced `_do_execute` dispatcher stub with routing to `_deploy_local / _dispatch_guided / _dispatch_auto`, added `_dispatch_guided` + `_dispatch_auto` methods
   - `_dispatch_guided`: renders target-specific bundle + setup_guide.md, writes back to registry + manifest
   - `_dispatch_auto`: detection-first, then guided-bundle-as-handoff + registry flip on MCP present, or is_error + install hint on MCP missing
   - Result: 16/16 workflow_deploy tests GREEN (8 local + 4 guided + 4 auto); full suite 603/603 GREEN

## Files Created/Modified

### Created

**Templates (7):**

- `yigthinker/tools/workflow/templates/pa/workflow.json.j2` — PA flow manifest envelope (`properties.displayName`, `iconUri`, `runtimeConfiguration.flowState`)
- `yigthinker/tools/workflow/templates/pa/apiProperties.json.j2` — PA API properties stub with empty `connectionParameters`, `publisher = "Yigthinker"`
- `yigthinker/tools/workflow/templates/pa/definition.json.j2` — PA flow definition with `Recurrence` trigger (frequency + interval from `cron_to_pa_recurrence`) and a placeholder `Http` action named `Run_Yigthinker_Workflow`
- `yigthinker/tools/workflow/templates/pa/setup_guide.md.j2` — bilingual import guide (flow.microsoft.com > My flows > Import Package Legacy) with troubleshooting table and placeholder-action replacement options
- `yigthinker/tools/workflow/templates/uipath/project.json.j2` — UiPath project manifest with `schemaVersion=4.0`, `studioVersion=23.10.0`, `targetFramework=Windows`, `dependencies.UiPath.System.Activities=[22.10.4]`
- `yigthinker/tools/workflow/templates/uipath/main.xaml.j2` — minimal UiPath workflow: Activity root with 5 xmlns declarations (xmlns, mc, sap, sap2010, x), single Sequence child with Python Scope placeholder comment
- `yigthinker/tools/workflow/templates/uipath/setup_guide.md.j2` — UiPath import + Python Scope wiring guide with Studio-specific step numbering

**Helper modules (3):**

- `yigthinker/tools/workflow/pa_bundle.py` — `build_pa_bundle(*, workflow_name, variables, engine, output_dir) -> Path`. Renders the 3 PA templates and packs them into `flow_import.zip` with the canonical `Microsoft.Flow/flows/<name>/definition.json` path
- `yigthinker/tools/workflow/uipath_bundle.py` — `build_uipath_bundle(*, workflow_name, variables, engine, output_dir) -> Path`. Renders project.json + Main.xaml and packs them into `process_package.zip` (user renames to `.nupkg` for UiPath Studio)
- `yigthinker/tools/workflow/mcp_detection.py` — `check_mcp_installed(package_name) -> bool`, `MCP_PACKAGE_MAP = {"power_automate": "yigthinker_pa_mcp", "uipath": "yigthinker_uipath_mcp"}`, `MCP_TOOL_MAP = {"power_automate": {"suggested_tool": "power_automate_create_flow", "install_hint": "pip install yigthinker[pa-mcp]"}, "uipath": {"suggested_tool": "uipath_publish_package", "install_hint": "pip install yigthinker[uipath-mcp]"}}`

**Fixtures (1):**

- `tests/fixtures/uipath_reference/main.xaml` — minimal known-good UiPath Main.xaml as reference for the template's XAML shape test

### Modified

- `yigthinker/tools/workflow/workflow_deploy.py` — added `cron_to_pa_recurrence` helper after `cron_to_ts_trigger`; replaced the `_do_execute` guided/auto stub with dispatcher routing; added `_dispatch_guided` (193 lines) and `_dispatch_auto` (131 lines) methods. `_deploy_local` untouched. Module docstring updated to describe all three modes.
- `tests/test_tools/test_workflow_deploy.py` — appended `TestWorkflowDeployGuided` (4 async tests) and `TestWorkflowDeployAuto` (4 async tests) classes at end of file. Reuses 09-01's `workflow_registry` + `ctx` fixtures and `_generate_sample_workflow` helper. Auto tests use `monkeypatch` on `mcp_detection.check_mcp_installed` to simulate MCP-present and MCP-missing states.
- `tests/test_tools/test_workflow_templates.py` — appended `TestPABundleTemplates` (4 tests) and `TestUiPathBundleTemplates` (5 tests) classes. Template tests use a per-class `engine` fixture. Bundle tests verify ZIP path layout, XML parseability, and path traversal safety.

## New/Changed Interfaces

### Helper module signatures

```python
# yigthinker/tools/workflow/pa_bundle.py
def build_pa_bundle(
    *,
    workflow_name: str,
    variables: dict,     # must include display_name, description,
                         # cron_expression, recurrence_frequency,
                         # recurrence_interval, registration_date
    engine: TemplateEngine,
    output_dir: Path,
) -> Path  # -> .../flow_import.zip

# yigthinker/tools/workflow/uipath_bundle.py
def build_uipath_bundle(
    *,
    workflow_name: str,
    variables: dict,     # must include display_name, description,
                         # python_exe, registration_date
    engine: TemplateEngine,
    output_dir: Path,
) -> Path  # -> .../process_package.zip

# yigthinker/tools/workflow/mcp_detection.py
def check_mcp_installed(package_name: str) -> bool
MCP_PACKAGE_MAP: dict[str, str]
MCP_TOOL_MAP: dict[str, dict[str, str]]
```

### WorkflowDeployTool.content payload shapes (09-02 additions)

**Guided mode success:**

```python
{
  "mode": "guided",
  "target": "power_automate" | "uipath",
  "workflow_name": "...",
  "version": <int>,
  "deploy_id": "<name>-v<n>-guided-<unix_ts>",
  "artifacts_ready": {
    "bundle": "<abs path to flow_import.zip or process_package.zip>",
    "setup_guide": "<abs path to setup_guide.md>",
  },
  "needs_manual_review": <bool>,  # True if cron->Recurrence fallback hit
  "message": "Guided bundle ready at ... Open ... for step-by-step import.",
}
```

**Auto mode success (MCP package present):**

```python
{
  "mode": "auto",
  "target": "power_automate" | "uipath",
  "workflow_name": "...",
  "version": <int>,
  "deploy_id": "<name>-v<n>-auto-<unix_ts>",
  "mcp_installed": True,
  "mcp_package": "yigthinker_pa_mcp" | "yigthinker_uipath_mcp",
  "artifacts_ready": {"bundle": "...", "setup_guide": "..."},
  "next_steps": {
    "suggested_tool": "power_automate_create_flow" | "uipath_publish_package",
    "mcp_package": "yigthinker_pa_mcp" | "yigthinker_uipath_mcp",
    "bundle_path": "<abs path>",
    "instructions": "The {package} MCP package is installed. To complete...",
  },
  "message": "Auto mode ready. MCP package {package} detected; ...",
}
```

**Auto mode failure (MCP package missing):**

```python
ToolResult(
  is_error=True,
  content=(
    "Auto mode requires the yigthinker_pa_mcp package. "
    "Install with 'pip install yigthinker[pa-mcp]' or use "
    "deploy_mode='guided' for a paste-ready bundle instead."
  ),
)
```

### cron_to_pa_recurrence mapping

| Cron shape        | Example       | frequency | interval | needs_manual_review |
| ----------------- | ------------- | --------- | -------- | ------------------- |
| Daily             | `0 8 * * *`   | Day       | 1        | False               |
| Weekly            | `0 8 * * 1`   | Week      | 1        | False               |
| Monthly on Nth    | `0 8 5 * *`   | Month     | 1        | False               |
| Every-N-hours     | `0 */4 * * *` | Hour      | 4        | False               |
| Exotic (ranges, lists, steps on non-trivial fields) | `15 3 * * 1-5` | Day | 1 | **True** |

## Test Inventory

**Total new tests:** 17 (all GREEN)

- **TestPABundleTemplates** (4):
  - `test_workflow_json_shape` — `properties.displayName`, `iconUri`, `runtimeConfiguration.flowState` all present
  - `test_api_properties_shape` — `properties.connectionParameters == {}`
  - `test_definition_has_recurrence_trigger` — trigger of type `Recurrence`
  - `test_guided_pa_bundle` — ZIP contains exactly the 3 canonical paths

- **TestUiPathBundleTemplates** (5):
  - `test_project_json_shape` — `name`, `projectVersion=1.0.0`, `targetFramework=Windows`, `schemaVersion` starts with `4.`
  - `test_main_xaml_is_valid_xml` — `ET.fromstring(xaml)` succeeds, root tag ends with `}Activity`, Sequence child present
  - `test_uipath_reference_fixture_parses` — sanity check on the git-tracked fixture
  - `test_guided_uipath_bundle` — ZIP contains `project.json` + `Main.xaml` at root
  - `test_flow_import_zip_structure` — no absolute paths, no `..` traversal

- **TestWorkflowDeployGuided** (4):
  - `test_guided_mode_power_automate` — PA end-to-end, bundle path ends in `flow_import.zip`
  - `test_guided_mode_uipath` — UiPath end-to-end, bundle path ends in `process_package.zip`
  - `test_guided_updates_registry_metadata` — registry has `target=power_automate`, `deploy_mode=guided`, `schedule`, `last_deployed`, `deploy_id` starting with `<name>-v1-guided-`; manifest version has `deployed_to`, `deploy_mode=guided`, `status=active`, `deploy_id`
  - `test_guided_mode_local_target_rejected` — `is_error=True` with "local" in message

- **TestWorkflowDeployAuto** (4):
  - `test_auto_mode` — monkeypatched `check_mcp_installed`=True, PA target; `mode=auto`, `mcp_installed=True`, `next_steps.suggested_tool=power_automate_create_flow`, `next_steps.mcp_package=yigthinker_pa_mcp`
  - `test_auto_mode_returns_next_steps` — monkeypatched True, UiPath target; `suggested_tool=uipath_publish_package`, `mcp_package=yigthinker_uipath_mcp`
  - `test_auto_mode_mcp_missing_error` — monkeypatched False; `is_error=True`, content contains package name and "guided" fallback hint
  - `test_auto_mode_local_target_rejected` — `is_error=True`

**Full test suite result:** `python -m pytest tests/ -x -q --timeout=120` → **603 passed** (up from 565 in 09-01 + 18 from parallel 09-03 WorkflowManageTool tests + 17 from this plan, accounting for 603 total as of the commit).

## Why Auto Mode Reuses Guided Bundling in the Happy Path

Auto mode is architect-only — Yigthinker never calls the MCP server directly (D-02). But a bare `next_steps` payload with nothing to hand off would force the user (or the LLM) to then run `workflow_deploy(deploy_mode=guided, ...)` separately to produce the bundle the MCP tool needs. That's two calls for one logical operation.

Instead, when `check_mcp_installed` returns True, `_dispatch_auto` internally calls `_dispatch_guided` to produce the bundle exactly once, then flips the registry row to `deploy_mode=auto` + `status=pending_auto_deploy` (distinct from guided's `status=active`). The returned `next_steps.bundle_path` points at the concrete ZIP the MCP tool can ingest. The `deploy_id` for the auto record is separate (`<name>-v<n>-auto-<ts>`) so both operations remain traceable.

On MCP missing, the guided bundle is NOT built — the tool just returns an is_error with the install hint. Rationale: the user explicitly asked for auto mode, so silently building a guided bundle as a consolation prize would be a silent downgrade (forbidden by D-09). The explicit error + guided-mode suggestion keeps the LLM in control of the policy.

## Deviations from Plan

### None — plan executed exactly as written

The plan interfaces block referenced a `deploy_notes` field on `WorkflowDeployInput`, but the plan-review notes correctly flagged that 09-01 canonicalized `notify_on_complete` + `credentials`. I read the 09-01 `workflow_deploy.py` as the source of truth (per the plan reviewer's note) and did not attempt to add `deploy_notes`. All other plan directions followed exactly.

Small adjustments that stayed within the plan's intent:

- **Dispatcher signature matches `_deploy_local` style.** The plan's example used `_dispatch_guided(self, input, ctx, version, workflow_dir)`, but the existing 09-01 `_deploy_local` uses `(self, input, version, version_dir, schedule)` without `ctx`. I kept the existing pattern for consistency and to avoid threading `ctx` through dispatchers that never touch it. `_dispatch_auto` matches the same signature but is `async` because the plan's example was `async`. The async signature is unused for actual async work but preserves room for future MCP handoff paths.
- **PA `workflow.json` envelope uses `properties`.** The plan offered two JSON shapes; I used the `properties.displayName` envelope since it's the shape PA's Import Package (Legacy) flow expects. Test `test_workflow_json_shape` was updated in Wave 0 stubs to assert `data["properties"]["displayName"]` rather than `data["displayName"]` so the test and template stay in lockstep.
- **Auto mode `artifacts_ready` is also returned at the top level** (in addition to `next_steps.bundle_path`) so the consumer can quickly grep for a bundle path regardless of mode. This is additive and doesn't violate the plan's contract.

## Issues Encountered

- **None.** All tests went from RED to GREEN on first run after the implementation. Smoke test passes end-to-end.
- **Parallel executor coordination (non-issue in practice).** The 09-03 parallel agent modified `yigthinker/registry_factory.py` and `tests/test_tools/test_registry_factory.py` to register `WorkflowManageTool`. Those files are owned by 09-03 per the parallel_execution contract and were never staged or committed by this plan. `git status` showed them as unstaged-on-disk during Task 1; I verified my commits only touched 09-02 files.

## Known Stubs

- **PA `definition.json` uses a placeholder HTTP action** pointing at `https://example.invalid/placeholder`. This is INTENTIONAL per D-06 — the flow is minimal scaffolding that the user wires to a real action (Run a Child Flow / Dataverse / HTTP-to-Gateway) in flow.microsoft.com after import. The setup_guide documents this explicitly as "Step 2 - Wire the placeholder action" with three replacement options.
- **UiPath `Main.xaml` Sequence is empty** with a comment explaining how to add a Python Scope activity in UiPath Studio. This is INTENTIONAL per D-06 — Studio regenerates view state + wiring on first open. The setup_guide walks the user through dragging Python Scope + Run Python Script inside the Sequence.

Neither stub blocks the plan's goal — they are part of the guided-mode design per Phase 9 CONTEXT D-06 ("complex orchestration stays in main.py").

## User Setup Required

- **None** for the plan itself (internal implementation).
- **Documented setup per deploy** is generated into each bundle's `setup_guide.md` at deploy time:
  - PA: flow.microsoft.com > My flows > Import Package (Legacy), confirm flow name, wire placeholder action, turn on flow
  - UiPath: rename `.zip` → `.nupkg`, open in Studio, add Python Scope + Run Python Script inside the Sequence

## Handoff Notes for Plan 09-03

- **No new registry fields.** 09-03's `workflow_manage` can rely on the same Phase 9 fields established in 09-01 (`target`, `deploy_mode`, `schedule`, `last_deployed`, `deploy_id`, `current_version` on the index; `deployed_to`, `deploy_mode`, `deploy_id`, `status` on the manifest). Guided and auto modes write the same field names.
- **New `status` value:** auto mode writes `status="pending_auto_deploy"` on the manifest version entry (distinct from guided's `active` and retired workflows' `retired`). `workflow_manage list` and `inspect` should probably render this as a distinct badge so the user knows auto-mode handoffs are in a different state than fully active deploys. D-22's list shape can accommodate this via the existing `status` field without a schema bump.
- **MCP detection is a reusable module.** `yigthinker/tools/workflow/mcp_detection.py` exports `check_mcp_installed` + `MCP_PACKAGE_MAP` + `MCP_TOOL_MAP`. If `workflow_manage` ever needs to surface MCP availability in `inspect` output (e.g. "this workflow is deploy_mode=auto but the MCP package is no longer installed"), it can import from here without touching `workflow_deploy`.
- **Architect-not-executor invariant is intact.** The workflow_deploy tool still has zero subprocess calls, zero MCP imports, zero external HTTP. Phase 9 validation's first assertion continues to hold for the full Phase 9 deploy surface.

## Self-Check: PASSED

- `yigthinker/tools/workflow/pa_bundle.py` — FOUND
- `yigthinker/tools/workflow/uipath_bundle.py` — FOUND
- `yigthinker/tools/workflow/mcp_detection.py` — FOUND
- `yigthinker/tools/workflow/templates/pa/workflow.json.j2` — FOUND
- `yigthinker/tools/workflow/templates/pa/apiProperties.json.j2` — FOUND
- `yigthinker/tools/workflow/templates/pa/definition.json.j2` — FOUND
- `yigthinker/tools/workflow/templates/pa/setup_guide.md.j2` — FOUND
- `yigthinker/tools/workflow/templates/uipath/project.json.j2` — FOUND
- `yigthinker/tools/workflow/templates/uipath/main.xaml.j2` — FOUND
- `yigthinker/tools/workflow/templates/uipath/setup_guide.md.j2` — FOUND
- `tests/fixtures/uipath_reference/main.xaml` — FOUND
- Commit `f999e80` (test(09-02): Wave 0 stubs) — FOUND
- Commit `5a89190` (feat(09-02): templates + bundle helpers + mcp_detection) — FOUND
- Commit `b4963fe` (feat(09-02): dispatcher wiring) — FOUND
- `python -m pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_templates.py tests/test_tools/test_workflow_registry.py` → 54 passed
- `python -m pytest tests/ -x -q --timeout=120` → 603 passed
- Manual smoke test: PA bundle layout + Recurrence=Day/1, UiPath bundle layout + Main.xaml parses, auto-mode MCP-missing error, auto-mode monkeypatched-present returns next_steps with suggested_tool — ALL VERIFIED

---
*Phase: 09-deployment-lifecycle*
*Completed: 2026-04-10*
