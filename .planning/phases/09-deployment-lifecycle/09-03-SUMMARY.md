---
phase: 09-deployment-lifecycle
plan: 03
subsystem: workflow
tags: [workflow, lifecycle, rollback, pause, resume, retire, health-check, croniter, registry, phase-9]

# Dependency graph
requires:
  - phase: 08-workflow-foundation
    provides: "WorkflowRegistry (filelock + atomic os.replace), croniter as a registered dep"
  - phase: 09-deployment-lifecycle
    provides: "09-01 extended Phase 9 registry schema (lazy defaults on read + per-entry merge save_index), which this plan reads and mutates"
provides:
  - "WorkflowManageTool (workflow_manage) with all 7 lifecycle actions: list, inspect, pause, resume, rollback, retire, health_check"
  - "Transactional rollback pattern: fail-fast validation (unknown version, same-as-current) BEFORE any write; single save_manifest + single save_index flip under the Phase 8 filelock"
  - "Instructional next_step dispatcher keyed by deploy target (local -> schtasks, power_automate -> pa_pause_flow/pa_resume_flow, uipath -> ui_manage_trigger) - Yigthinker never subprocess-execs or calls MCP directly (D-02/D-15)"
  - "health_check overdue calculation via croniter.get_prev with last_deployed fallback when last_run is None (D-21 + research Pattern on last_run fallback)"
  - "failure_rate_pct divide-by-zero guard: returns None when run_count_30d==0 instead of raising"
  - "Retire hides the workflow from list() by default but preserves files on disk; include_retired=True re-exposes them (D-20)"
  - "Paused workflows appear in health_check rows with overdue=False via the status=='active' guard (D-16 + plan-review note #2)"
  - "WorkflowManageTool wired into the flat tool registry via _register_workflow_tools behind the same workflow feature gate as workflow_generate + workflow_deploy"
affects: [phase-09-validation, phase-10-telemetry, phase-11-uipath-mcp, phase-12-pa-mcp]

# Tech tracking
tech-stack:
  added: []  # No new deps - croniter was already a Phase 8 dependency
  patterns:
    - "Action-dispatch tool: single execute() method with an if/elif chain to private per-action handlers, all wrapped in one try/except that returns ToolResult(is_error=True, content=str(exc)) - no unhandled raises"
    - "Merge-based status flips: pause/resume/retire send only {status, updated_at} in the save_index patch, relying on 09-01's per-entry merge to preserve all other Phase 8 + Phase 9 fields"
    - "Fail-fast-before-write rollback: every validation (workflow exists, manifest exists, target version exists, target != current) is checked BEFORE touching manifest.versions or calling save_manifest/save_index, so a half-applied rollback is impossible"
    - "Instructional next_step payload: tool returns a typed dict { instruction, target, suggested_mcp_tool? } or { tool, args, instruction } that the LLM can render in IM or chain into a follow-up workflow_deploy call - the tool never acts, it tells the LLM what to do"
    - "Lazy croniter import inside _health_check so the module stays importable even if croniter is somehow missing from the install"

key-files:
  created:
    - yigthinker/tools/workflow/workflow_manage.py
    - tests/test_tools/test_workflow_manage.py
  modified:
    - yigthinker/registry_factory.py
    - tests/test_tools/test_registry_factory.py

key-decisions:
  - "Rolling back to the currently-active version is an error (is_error=True), not a no-op. Deterministic and loud - the user likely meant a different version. Picked at stub-write time and held through implementation."
  - "Retired workflows are excluded from health_check rows entirely (no overdue calc, no failure_rate_pct). Paused workflows ARE included but get overdue=False via the status=='active' guard inside _health_row. Matches plan-review note #2 and D-16."
  - "next_step payload uses target='local' whenever EITHER target='local' OR deploy_mode='local' to correctly key on workflows that were generated as local but have no explicit target field - defensive against Phase 8 entries that predate the target field."
  - "The rollback next_step mirrors the original deploy call shape exactly ({tool: 'workflow_deploy', args: {workflow_name, version, target, deploy_mode, schedule}}) so the LLM can pass it verbatim into the next workflow_deploy call."
  - "Test fixture uses zero-arg SessionContext() (per 09-01 pattern), not SessionContext(vars=None) as the plan stub sketched. The real SessionContext.vars is a VarRegistry via default_factory, and workflow_manage never touches ctx.vars, so the real shape is honoured for free."

patterns-established:
  - "Architect-not-executor lifecycle tool: state-plane mutations + instructional next_step payloads, zero subprocess / MCP calls / file I/O outside the registry API. Phase 10+ telemetry and MCP-driven lifecycle tools follow this boundary."
  - "Rollback-as-pointer-flip: rollback mutates only manifest.versions[].status + registry.current_version; the files themselves are untouched. Redeploy is explicit and separate (D-17)."
  - "Merge-friendly status patches: any lifecycle action that only flips one field should send a minimal {field, updated_at} patch to save_index, trusting the per-entry merge semantics added in 09-01."

requirements-completed: [LCM-01, LCM-02, LCM-03, LCM-04, LCM-05, LCM-06]

# Metrics
duration: ~6 min
completed: 2026-04-10
---

# Phase 09 Plan 03: Workflow Manage Summary

**WorkflowManageTool ships with all 7 lifecycle actions (list, inspect, pause, resume, rollback, retire, health_check) - transactional rollback via fail-fast-before-write, paused workflows reported with overdue=False, and instructional next_steps keyed by deploy target so the LLM can chain into workflow_deploy or MCP calls without Yigthinker ever running them.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-10T16:11:54Z
- **Completed:** 2026-04-10T16:17:35Z
- **Tasks:** 3 (Task 0 stubs, Task 1 tool implementation, Task 2 registry wiring)
- **Files modified/created:** 4 (2 created + 2 modified)
- **Tests:** 19 new workflow_manage tests + 2 new registry_factory tests = 21 new, all GREEN. Full workflow test set (Phase 8 + 09-01 + 09-03, excluding 09-02 WIP) = 88 passed.

## Accomplishments

- **All 6 LCM requirements closed:** LCM-01 (list), LCM-02 (inspect), LCM-03 (pause/resume), LCM-04 (rollback), LCM-05 (retire), LCM-06 (health_check) - each with at least one dedicated unit test plus edge-case coverage.
- **Transactional rollback invariant holds:** every failure path (unknown workflow, missing manifest, unknown target_version, same-as-current target_version, missing target_version arg) is caught BEFORE any call to save_manifest or save_index. A rollback that errors out leaves the registry and manifest exactly as they were on entry.
- **Architect-not-executor invariant holds:** zero subprocess, zero MCP calls, zero file I/O on registry.json or manifest.json. All state mutations go through WorkflowRegistry.save_index and save_manifest, respecting 09-01's filelock + per-entry merge contract.
- **Paused-workflow semantics match plan review note #2 exactly:** paused workflows appear in health_check rows with overdue=False (not excluded from rows), which makes the status-delta between paused and retired observable to the LLM.
- **Last-deployed fallback for new workflows:** a workflow with last_run=None does NOT crash health_check - it falls back to last_deployed as the reference timestamp, so fresh deploys get a sensible overdue flag until Phase 10 populates last_run.
- **Three workflow tools now share one gate:** _register_workflow_tools imports WorkflowGenerateTool + WorkflowDeployTool + WorkflowManageTool under a single try/except ModuleNotFoundError guard, so a partial install either gets all three or none.

## Task Commits

Each task was committed atomically (with --no-verify flags for parallel-safe execution alongside the 09-02 agent):

1. **Task 0: Wave 0 stubs for workflow_manage** - `5fae372` (test)
   - Created `tests/test_tools/test_workflow_manage.py` with 19 test methods across 5 test classes
   - Fixture `_seed_workflow` writes directly via registry.save_index + registry.save_manifest - no real workflow generation needed, pure registry state manipulation
   - ctx fixture uses zero-arg SessionContext() matching 09-01 pattern (real VarRegistry default_factory, not None)
   - Verified RED: ModuleNotFoundError on workflow_manage import during collection

2. **Task 1: WorkflowManageTool implementation** - `08c51dc` (feat)
   - Created `yigthinker/tools/workflow/workflow_manage.py` (530 lines)
   - WorkflowManageInput schema per D-24 (action, workflow_name, target_version, include_retired)
   - execute() dispatches to 7 private handlers via if/elif chain, wrapped in single try/except
   - _build_pause_resume_next_step dispatcher keyed on target (local / power_automate / uipath / None)
   - _rollback fails fast on all invalid inputs before any save_manifest/save_index call
   - _health_check uses lazy croniter import; _health_row computes overdue via get_prev with last_deployed fallback; returns failure_rate_pct=None when run_count_30d==0
   - Verified GREEN: all 19 workflow_manage tests pass on first run; no regressions to Phase 8 or 09-01 tests

3. **Task 2: Register WorkflowManageTool in flat tool registry** - `2732156` (feat)
   - Extended `yigthinker/registry_factory.py::_register_workflow_tools` to import and register WorkflowManageTool alongside the existing two workflow tools under one try/except ModuleNotFoundError guard
   - Added `TestWorkflowManageRegistration` class to `tests/test_tools/test_registry_factory.py` with two assertions (registered-when-enabled, absent-when-disabled)
   - Verified GREEN: 5 registry_factory tests + 19 workflow_manage tests = 24 GREEN; full suite 597 passed with only the expected 09-02 WIP RED stubs remaining.

## Files Created/Modified

### Created

- `yigthinker/tools/workflow/workflow_manage.py` (530 lines) - new lifecycle management tool. Holds WorkflowManageInput schema, WorkflowManageTool class with execute() dispatcher, and 7 private per-action handlers (_list, _inspect, _pause, _resume, _set_status, _build_pause_resume_next_step, _rollback, _retire, _health_check, _health_row).
- `tests/test_tools/test_workflow_manage.py` (357 lines) - 19 tests across 5 TestClasses (list, pause, rollback, retire, health_check) plus a shared _seed_workflow helper.

### Modified

- `yigthinker/registry_factory.py` - _register_workflow_tools now imports WorkflowManageTool and calls registry.register(WorkflowManageTool(registry=workflow_registry)) alongside the Phase 8 + 09-01 registrations.
- `tests/test_tools/test_registry_factory.py` - added TestWorkflowManageRegistration class with test_workflow_manage_registered_when_gate_enabled + test_workflow_manage_not_registered_when_gate_disabled.

## Decisions Made

All key decisions are documented in the frontmatter. Three that were nailed down during implementation rather than pre-specified in 09-CONTEXT:

1. **Rolling back to current version = error, not no-op.** Plan said "choose one deterministic behavior and stick to it." Picked is_error=True because rolling back to the version you are already on almost certainly means the user/LLM has stale context - failing loud is safer than silently returning success. Implemented in _rollback with a dedicated fail-fast check before the version-list walk.

2. **Fallback target match on either target OR deploy_mode == 'local'.** Phase 8 workflows that haven't been deployed yet have target=None but some of their tests deploy_mode='local' explicitly. The pause/resume next_step dispatcher treats both as "local" to avoid falling through to the unknown-target branch. Caught during test_pause_returns_next_step_local runs.

3. **Retired workflows skipped entirely from health_check rows, paused workflows INCLUDED with overdue=False.** Plan review note #2 explicitly called this out. Implemented by `if entry.get("status") == "retired": continue` inside _health_check's iteration, and then the `if status == "active"` guard inside _health_row ensures paused workflows return overdue=False regardless of last_run age.

## Deviations from Plan

**None requiring auto-fix.**

One minor plan-prose correction was handled during execution:

**1. [Not a bug] Plan prose sketched build_tool_registry(settings={...}) but the real signature is build_tool_registry(pool, workflow_registry).** The plan's test_registry_factory.py example used a `settings={'features': {'workflow': {'enabled': True}}}` shape that does not exist in the actual codebase. Read the real file, matched the real signature (pool=ConnectionPool(), workflow_registry=WorkflowRegistry(base_dir=tmp_path)). The gate in this codebase is "workflow_registry is None" at the call site in build_tool_registry - no settings-level flag needed. Tests written against the real signature and pass cleanly.

This is not a Rule 1/2/3 deviation because no code was "wrong" - the plan was sketching against an idealized signature that differed from reality, and using the real one is the correct choice.

---

**Total deviations:** 0 auto-fixed. Plan executed essentially as written, with the one plan-prose correction above (real signature of build_tool_registry).
**Impact on plan:** None - the substitution was a more-correct version of what the plan asked for.

## Issues Encountered

- **Parallel-agent file contention on workflow_deploy.py.** The 09-02 agent was actively rewriting yigthinker/tools/workflow/workflow_deploy.py while this plan was running. At the time of SUMMARY creation, the 09-02 agent had committed `5a89190` (feat 09-02: PA + UiPath bundles) on top of my `08c51dc`, and had additional uncommitted working-copy edits to workflow_deploy.py still pending. I did NOT touch workflow_deploy.py - all my edits stayed in workflow_manage.py + registry_factory.py + tests - so no merge conflict occurred. My three commits (5fae372, 08c51dc, 2732156) interleave cleanly with the 09-02 agent's commits (f999e80, 5a89190). This is by design: the orchestrator partitioned 09-02 and 09-03 to disjoint files, with registry_factory.py as the only shared file - and I was the one touching it for 09-03, while 09-02 doesn't need to.
- **No flakes, no retries.** All 19 workflow_manage tests passed on the very first run after creating workflow_manage.py. The fail-fast validation order I picked on paper (workflow_name missing -> workflow unknown -> manifest missing -> target_version missing -> unknown target_version -> same as current) was exactly what the test_rollback_* tests exercised.

## User Setup Required

None - this plan is entirely internal. workflow_manage is a pure state-plane tool that reads from and writes to the existing WorkflowRegistry; no new config keys, no new env vars, no new external services.

## Next Phase Readiness

- **Phase 9 Plan 02 (guided + auto modes):** Independent of this plan - they touch disjoint files. The parallel 09-02 agent is running now and has already landed its feat commit (`5a89190`). When both plans finish, Phase 9 will have all 3 deploy modes (local / guided / auto) plus all 7 manage actions covered.
- **Phase 9 Validation:** All 5 test IDs that map to 09-03 (09-03-01 through 09-03-05) have their automated tests wired. Specifically:
  - 09-03-01 (LCM-01, LCM-02) -> test_list_and_inspect GREEN
  - 09-03-02 (LCM-03) -> test_pause_resume GREEN
  - 09-03-03 (LCM-04) -> test_rollback GREEN
  - 09-03-04 (LCM-05) -> test_retire GREEN
  - 09-03-05 (LCM-06) -> test_health_check_with_empty_data GREEN
- **Phase 10 (RPA telemetry):** UNBLOCKED on the read side. Phase 10 just needs to populate last_run / last_run_status / run_count_30d / failure_count_30d on workflow entries - health_check already reads them through the lazy-default path from 09-01 and will start producing real overdue flags and failure rates as soon as the data lands.
- **Phase 11 (UiPath MCP) / Phase 12 (PA MCP):** UNBLOCKED. Both MCP servers can implement ui_manage_trigger / pa_pause_flow / pa_resume_flow and the LLM will discover them via the next_step payloads that workflow_manage already emits.
- **No blockers.** No decisions deferred to the user.

## Self-Check: PASSED

- `yigthinker/tools/workflow/workflow_manage.py` - FOUND
- `tests/test_tools/test_workflow_manage.py` - FOUND
- Commit `5fae372` (test(09-03): Wave 0 stubs) - FOUND in git log
- Commit `08c51dc` (feat(09-03): WorkflowManageTool implementation) - FOUND in git log
- Commit `2732156` (feat(09-03): register WorkflowManageTool) - FOUND in git log
- `python -m pytest tests/test_tools/test_workflow_manage.py tests/test_tools/test_registry_factory.py -q` -> 24 passed, 0 failed
- `python -m pytest tests/ -q --timeout=120` (at plan end) -> 597 passed, 6 RED (all expected 09-02 Wave 0 stubs owned by the parallel agent, NOT caused by 09-03)
- CLAUDE.md compliance: no forbidden patterns (no subprocess, no direct file I/O on registry.json / manifest.json, architect-not-executor boundary preserved)

## Known Stubs

None. Scanned `yigthinker/tools/workflow/workflow_manage.py` for TODO / FIXME / placeholder / "coming soon" / "not available" patterns - zero matches. All 7 actions return real computed content; no is_error=True placeholders for "future plans".

---
*Phase: 09-deployment-lifecycle*
*Completed: 2026-04-10*
