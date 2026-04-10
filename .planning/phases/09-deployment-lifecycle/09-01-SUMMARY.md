---
phase: 09-deployment-lifecycle
plan: 01
subsystem: workflow
tags: [workflow, deploy, jinja2, cron, task-scheduler, registry, phase-9, lazy-defaults, template-engine]

# Dependency graph
requires:
  - phase: 08-workflow-foundation
    provides: "WorkflowRegistry (filelock + atomic os.replace, Phase 8 schema), TemplateEngine (SandboxedEnvironment + AST validator + credential scanner), WorkflowGenerateTool (creates v1 bundles used as deploy inputs)"
provides:
  - "WorkflowDeployTool with local deploy_mode fully implemented end-to-end"
  - "cron_to_ts_trigger dispatcher mapping 5-field cron expressions to Task Scheduler calendar trigger kinds (daily / monthly / weekly / hourly) with fallback + needs_manual_review flag"
  - "Phase 9 lazy-default reads on WorkflowRegistry.load_index() and get_manifest() so Phase 8 entries gain target/deploy_mode/schedule/deploy_id/current_version/... fields without disk writeback (D-13)"
  - "Per-entry merge save_index so Phase 9 patches preserve Phase 8 fields (latest_version, created_at, ...)"
  - "TemplateEngine.render_text() for non-Python artifacts — SandboxedEnvironment render + credential scanner, skips Python AST validator (D-09)"
  - "Three local-mode Jinja2 templates: task_scheduler.xml.j2 (Task Scheduler v1.3), crontab.txt.j2 (POSIX cron), setup_guide.md.j2 (install instructions for both schedulers)"
  - "WorkflowDeployTool wired into flat tool registry via _register_workflow_tools behind the same workflow feature gate as workflow_generate"
affects: [09-02-guided-auto, 09-03-workflow-manage, phase-09-validation]

# Tech tracking
tech-stack:
  added:
    - croniter (Phase 8 dep, first use in Phase 9 for schedule validation + next-run calculation)
  patterns:
    - "Lazy-default-on-read: _fill_*_defaults() helpers fill Phase N+1 fields without touching disk; writeback only happens on the first Phase N+1 save (D-13)"
    - "Per-entry merge under filelock: save_index walks workflows patch dict and updates existing entries in place instead of wholesale replace — preserves prior-phase fields transparently"
    - "render_text() escape hatch on TemplateEngine — re-uses SandboxedEnvironment loader but skips Python AST validator for XML/crontab/markdown output"
    - "Architect-not-executor deploy tool — render + write metadata, never run schtasks or crontab; LLM or user runs the scheduler install step from setup_guide.md"
    - "Dual python_exe context (python_exe_windows + python_exe_posix) so the same deploy bundle produces Windows and POSIX artifacts cleanly (Pitfall 7)"

key-files:
  created:
    - yigthinker/tools/workflow/workflow_deploy.py
    - yigthinker/tools/workflow/templates/local/task_scheduler.xml.j2
    - yigthinker/tools/workflow/templates/local/crontab.txt.j2
    - yigthinker/tools/workflow/templates/local/setup_guide.md.j2
    - tests/test_tools/test_workflow_deploy.py
  modified:
    - yigthinker/tools/workflow/registry.py
    - yigthinker/tools/workflow/template_engine.py
    - yigthinker/registry_factory.py
    - tests/test_tools/test_workflow_registry.py
    - tests/test_tools/test_workflow_templates.py
    - tests/test_tools/test_registry_factory.py

key-decisions:
  - "Lazy defaults on read only — never write back Phase 9 fields to Phase 8 entries until the first real Phase 9 save, so mixed-phase registries stay readable (D-13)"
  - "save_index switched to per-entry merge — Phase 8's wholesale dict.update() would drop latest_version/created_at when a Phase 9 patch arrived, so merge per workflow entry instead"
  - "cron_to_ts_trigger dispatcher uses canonical-shape matching plus a calendar_daily fallback with needs_manual_review=True — avoids the dragon of fully general cron→Windows translation while still producing a loadable XML for exotic schedules"
  - "Separate python_exe_windows vs python_exe_posix in the render context so the crontab never contains backslashes on Windows generators (Pitfall 7 guard)"
  - "Credential validator rejects any value not starting with vault:// or {{ — catches plaintext leaks at tool entry before any template render"
  - "deploy_id format {name}-v{n}-{mode}-{unix_ts} (D-28) — human-readable and grep-friendly"
  - "Guided + auto modes return is_error=True with 'see Plan 09-02' so 09-02 can implement them without replacing a stub ToolResult shape that consumers already depend on"
  - "No subprocess, no MCP calls, no scheduler invocation from the tool — strictly architect-not-executor per Phase 9 CONTEXT invariant"

patterns-established:
  - "Phase-N lazy-default-on-read upgrade path: add _PHASE{N}_*_DEFAULTS + _fill_*_entry_defaults() module-level helpers, call them in load_* methods, leave save_* merge-based so first Phase-N write naturally upgrades the entry"
  - "TemplateEngine has two render surfaces: render/render_checkpoint_utils/render_config/render_requirements (Python, AST-validated) and render_text (non-Python, scanner-only)"
  - "Deploy tool bundle layout: {base}/{name}/v{version}/local_guided/ holds the local-mode artifacts; Plan 09-02 will add sibling directories for guided/auto modes"
  - "Task 0 Wave 0 RED stub pattern continues from Phase 8: put all tool imports *inside* test bodies so collection-time ImportError becomes test-time ImportError"

requirements-completed: [DEP-01, DEP-04, DEP-05]

# Metrics
duration: ~90 min (across resumption)
completed: 2026-04-10
---

# Phase 09 Plan 01: Deployment Lifecycle Foundation Summary

**WorkflowDeployTool local mode end-to-end: renders Task Scheduler XML + POSIX crontab + setup guide into v{n}/local_guided/, writes Phase 9 deploy metadata back to registry.json + manifest.json, with a lazy-default read upgrade path so Phase 8 entries stay compatible.**

## Performance

- **Duration:** ~90 min (split across a context compaction mid-Task-1)
- **Completed:** 2026-04-10T12:14Z
- **Tasks:** 3 (Task 0 stubs, Task 1 registry + template engine + templates, Task 2 deploy tool + registry_factory wiring)
- **Files modified/created:** 11 source + test files
- **Tests:** 40 workflow-related tests pass; full suite 565/565 green

## Accomplishments

- WorkflowDeployTool ships with local mode fully wired. User can call it against any Phase 8 workflow and get a task_scheduler.xml, crontab.txt, and setup_guide.md bundle ready to paste-and-install on either Windows or POSIX.
- Phase 9 registry schema is live via lazy-default-on-read (D-13) — existing Phase 8 entries automatically look Phase-9-shaped to callers without any disk migration, while the first real Phase 9 write naturally upgrades the entry on disk.
- Per-entry merge in save_index fixes a subtle prior-phase-field-erasure hazard: Phase 9 patches now preserve latest_version / created_at / updated_at transparently.
- cron_to_ts_trigger dispatcher handles the four canonical 5-field cron shapes (daily / monthly-on-Nth / weekly-on-W / every-N-hours) with a documented fallback + needs_manual_review flag for exotic shapes.
- TemplateEngine gains a second rendering surface (render_text) without weakening the Python AST validator for workflow scripts — non-Python templates get the credential scanner only.
- WorkflowDeployTool is wired into the flat tool registry alongside workflow_generate behind the same workflow feature gate — registered when Jinja2 is importable, skipped otherwise.

## Task Commits

Each task was committed atomically:

1. **Task 0: Wave 0 RED stubs** — `9e435b1` (test)
   - `tests/test_tools/test_workflow_deploy.py` — 8 RED stubs (local mode, XML/crontab shape, cron dispatcher, target/mode combo, invalid schedule fail-fast, registry + manifest write-back)
   - `tests/test_tools/test_workflow_registry.py` — 3 stubs (lazy defaults on read, corruption propagation, extended fields write-through merge)
   - `tests/test_tools/test_workflow_templates.py` — 3 stubs (render_text skips AST, render_text runs credential scanner, all 3 local templates render cleanly)
   - `tests/test_tools/test_registry_factory.py` — 1 stub (workflow_deploy registered)

2. **Task 1: Registry lazy defaults + render_text + local templates** — `64dd05d` (feat)
   - `registry.py` — _PHASE9_WORKFLOW_DEFAULTS / _PHASE9_VERSION_DEFAULTS module constants, _fill_workflow_entry_defaults + _fill_version_entry_defaults helpers, load_index + get_manifest call them on read, save_index switched to per-entry merge
   - `template_engine.py` — render_text method (SandboxedEnvironment + credential scanner, skips AST validator)
   - `templates/local/task_scheduler.xml.j2` — Task Scheduler v1.3 XML with conditional trigger dispatch on trigger.kind
   - `templates/local/crontab.txt.j2` — POSIX cron with explicit PATH, cd + python + log redirect
   - `templates/local/setup_guide.md.j2` — bilingual install guide

3. **Task 2: WorkflowDeployTool local mode + cron dispatcher + registry_factory** — `b79bf67` (feat)
   - `workflow_deploy.py` — WorkflowDeployInput schema, cron_to_ts_trigger dispatcher, _validate_credentials, _make_deploy_id, WorkflowDeployTool class with execute/_do_execute/_deploy_local
   - `registry_factory.py` — _register_workflow_tools extended to import and register WorkflowDeployTool

## Files Created/Modified

### Created

- `yigthinker/tools/workflow/workflow_deploy.py` — new deploy tool (372 lines); holds WorkflowDeployInput, cron_to_ts_trigger, _validate_credentials, _make_deploy_id, and WorkflowDeployTool with local mode wired to TemplateEngine.render_text and WorkflowRegistry.save_index/save_manifest
- `yigthinker/tools/workflow/templates/local/task_scheduler.xml.j2` — Task Scheduler 1.3 XML template; trigger dispatcher maps trigger.kind to ScheduleByDay / ScheduleByMonth / ScheduleByWeek / ScheduleByDay+Repetition
- `yigthinker/tools/workflow/templates/local/crontab.txt.j2` — POSIX crontab template with explicit PATH and cd + main.py + >> run.log 2>&1
- `yigthinker/tools/workflow/templates/local/setup_guide.md.j2` — markdown guide explaining schtasks /create /xml on Windows and crontab crontab.txt on POSIX
- `tests/test_tools/test_workflow_deploy.py` — 8 tests covering the full local mode path plus the cron dispatcher unit

### Modified

- `yigthinker/tools/workflow/registry.py` — added Phase 9 default constants + fill helpers; load_index + get_manifest now fill defaults on read; save_index switched to per-entry merge (preserves Phase 8 fields through Phase 9 patches)
- `yigthinker/tools/workflow/template_engine.py` — added render_text method for non-Python artifacts
- `yigthinker/registry_factory.py` — _register_workflow_tools now also registers WorkflowDeployTool
- `tests/test_tools/test_workflow_registry.py` — added test_lazy_defaults_on_read, test_lazy_defaults_do_not_swallow_corruption, test_extended_fields_write_through
- `tests/test_tools/test_workflow_templates.py` — added test_render_text_skips_ast, test_render_text_runs_credential_scanner, test_local_scheduler_templates
- `tests/test_tools/test_registry_factory.py` — added test_workflow_deploy_registered

## Decisions Made

All key decisions are documented in the frontmatter key-decisions list. The two decisions not pre-specified in 09-CONTEXT were:

1. **save_index per-entry merge (not in CONTEXT)** — Discovered during Task 1 verification: the original wholesale `current["workflows"].update(patch["workflows"])` would drop `latest_version` / `created_at` / `updated_at` when a Phase 9 deploy patch arrived carrying only Phase 9 fields. The test_extended_fields_write_through stub caught it. Switched to per-entry merge inside the existing filelocked section, preserving Phase 8 fields without any callsite change. This is a stricter but equivalent contract for Phase 8 callers (who already supplied full entries) and a necessary one for Phase 9 patches.

2. **Dual python_exe context (not in CONTEXT)** — The initial implementation passed a single python_exe to all three templates. test_crontab_txt_shape caught it: on Windows the sys.executable is `C:\Program Files\Python311\python.exe`, which smuggled backslashes into the POSIX crontab output. Split into `python_exe_windows` (native) and `python_exe_posix` (Path.as_posix()) so the XML and the crontab each get the shape that matches where they'll run. Pitfall 7 guard made literal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Per-entry merge in save_index to preserve Phase 8 fields**
- **Found during:** Task 1 verification (test_extended_fields_write_through failed with KeyError: 'latest_version')
- **Issue:** Phase 8's `current["workflows"].update(data.get("workflows", {}))` replaces entire workflow dicts. A Phase 9 patch carrying only Phase 9 fields would erase `latest_version`, `created_at`, `updated_at` etc. This is invisible in Phase 8 because every Phase 8 caller passes a complete dict, but the new Phase 9 patch style breaks it.
- **Fix:** Walk `data.get("workflows", {})` and call `existing.update(wf_patch)` per workflow name so Phase 8 fields survive Phase 9 writes. Still inside the same filelock.
- **Files modified:** `yigthinker/tools/workflow/registry.py`
- **Verification:** test_extended_fields_write_through GREEN; test_concurrent_writes still GREEN (the merge doesn't change concurrency semantics)
- **Committed in:** `64dd05d` (Task 1 commit)

**2. [Rule 1 - Bug] Dual python_exe context (posix-slashed variant for crontab)**
- **Found during:** Task 2 verification (test_crontab_txt_shape failed with `'\\' is contained here`)
- **Issue:** Windows sys.executable contains backslashes. Passing it into the crontab template produced a path with `\` separators in POSIX output.
- **Fix:** Added `python_exe_windows = sys.executable` and `python_exe_posix = Path(sys.executable).as_posix()`. XML context uses the Windows variant, crontab context uses the POSIX variant.
- **Files modified:** `yigthinker/tools/workflow/workflow_deploy.py`
- **Verification:** test_crontab_txt_shape GREEN; all 8 workflow_deploy tests GREEN
- **Committed in:** `b79bf67` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs caught by Wave 0 tests going RED→GREEN)
**Impact on plan:** Both fixes were essential for correctness. No scope creep — both are guard-rails the plan's Wave 0 tests were explicitly written to catch.

## Issues Encountered

- **Flaky `test_concurrent_writes` on Windows (pre-existing, unrelated to this plan).** On one of the full-suite runs, `test_concurrent_writes` hit a `PermissionError` on `registry.json` inside the ThreadPoolExecutor fan-out. Running it in isolation and re-running the full suite both passed cleanly (565/565 twice). Root cause is Windows-specific file-lock race between filelock's lock file and `json.load_text` reads in the worker threads. Pre-existing Phase 8 test, pre-existing Phase 8 code path (I did not touch concurrency semantics in save_index). Logging here so Phase 9 Plan 02 is aware if it reappears.
- **Context compaction mid-Task-1.** The initial pass wrote all Task 1 artifacts (registry edits, template_engine edit, three templates) but hit the output limit before running the verification. Resumed, ran the 6 Task 1 tests, hit the save_index merge bug described above, fixed it, GREEN. No work was lost.

## Known Stubs

None that block the plan's objective. The two deliberate placeholder return paths are:

- `WorkflowDeployTool._do_execute` returns `ToolResult(is_error=True, content="deploy_mode='...' is not yet implemented in Plan 09-01 - see Plan 09-02")` for `deploy_mode in {guided, auto}`. This is intentional — Plan 09-02 fills these in. The ToolResult shape is stable so 09-02 can swap the body without breaking callers that already handle is_error=True.

## User Setup Required

None — this plan is entirely internal. The user-facing artifacts (task_scheduler.xml, crontab.txt, setup_guide.md) are generated per-workflow at deploy time, not installed as part of the plan.

## Next Phase Readiness

- **Plan 09-02 (guided + auto modes):** unblocked. Can now extend `_do_execute` to dispatch `deploy_mode == "guided"` and `deploy_mode == "auto"` without touching registry schema, template engine, or the flat registry wiring.
- **Plan 09-03 (workflow_manage):** unblocked on the registry side. `WorkflowRegistry.load_index()` now returns Phase 9 shaped entries so `workflow_manage list` can show deploy_mode / last_deployed / current_version without a schema bump.
- **Phase 9 validation:** the "architect-not-executor" invariant is preserved — no subprocess, no scheduler install, no MCP call. Phase 9 VALIDATION.md's first assertion holds.
- **No blockers.**

## Self-Check: PASSED

- `yigthinker/tools/workflow/workflow_deploy.py` — FOUND
- `yigthinker/tools/workflow/templates/local/task_scheduler.xml.j2` — FOUND
- `yigthinker/tools/workflow/templates/local/crontab.txt.j2` — FOUND
- `yigthinker/tools/workflow/templates/local/setup_guide.md.j2` — FOUND
- `tests/test_tools/test_workflow_deploy.py` — FOUND
- Commit `9e435b1` (test(09-01): Wave 0 stubs) — FOUND
- Commit `64dd05d` (feat(09-01): registry + render_text + templates) — FOUND
- Commit `b79bf67` (feat(09-01): WorkflowDeployTool local mode) — FOUND
- `python -m pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_registry.py tests/test_tools/test_workflow_templates.py tests/test_tools/test_registry_factory.py -q` → 40 passed
- `python -m pytest tests/ -q --timeout=120` → 565 passed (confirmed twice)

---
*Phase: 09-deployment-lifecycle*
*Completed: 2026-04-10*
