---
phase: 10-gateway-rpa-behavior
plan: 03
subsystem: behavior-layer
tags: [patterns, filelock, pydantic, importlib, tempfile, atomic-write, feature-gate]

# Dependency graph
requires:
  - phase: 05-session-memory-auto-dream
    provides: filelock dependency, AutoDream skeleton that 10-04 will extend
  - phase: 08-workflow-foundation
    provides: WorkflowRegistry.save_index atomic-write pattern, workflow feature gate
  - phase: 09-deployment-lifecycle
    provides: importlib.util.find_spec MCP detection pattern (cloned from Phase 9 auto mode)
provides:
  - PatternStore filelocked JSON store at ~/.yigthinker/patterns.json with lazy suppression expiry
  - SuggestAutomationTool (BHV-03 + BHV-04 read-side contract)
  - gates.behavior feature gate in DEFAULT_SETTINGS
  - AppContext.pattern_store field wired through builder.py for Plan 10-04 AutoDream attachment
  - build_tool_registry + _register_workflow_tools pattern_store kwarg
affects: [10-04, Phase 11, Phase 12]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic JSON writes via tempfile.mkstemp + os.replace under filelock (clone of WorkflowRegistry.save_index)"
    - "Pitfall 5 mitigation: _save_locked helper for FileLock reentrancy avoidance"
    - "CORR-04a lazy suppression pruning at read time (mirror of EventDeduplicator._prune)"
    - "importlib.util.find_spec for MCP package detection without triggering imports (Phase 9 auto-mode clone)"
    - "Disjoint-subkey additive edits to DEFAULT_SETTINGS for parallel-wave merge safety"

key-files:
  created:
    - yigthinker/memory/patterns.py
    - yigthinker/tools/workflow/suggest_automation.py
    - tests/test_memory/test_patterns.py
    - tests/test_tools/test_suggest_automation.py
    - .planning/phases/10-gateway-rpa-behavior/deferred-items.md
  modified:
    - yigthinker/settings.py
    - yigthinker/builder.py
    - yigthinker/registry_factory.py

key-decisions:
  - "CORR-04a: Lazy suppression pruning happens inside list_active/list_patterns under the file lock; no background sweeper"
  - "Pitfall 5: suppress() acquires the lock once and calls _save_locked helper to prevent nested FileLock acquisition"
  - "can_deploy_to computed via importlib.util.find_spec — never imports MCP modules"
  - "gates.behavior is a simple toggle; 10-01 owns top-level DEFAULT_SETTINGS['behavior'] block (disjoint subkeys)"
  - "Test helper uses zero-arg SessionContext() — matches test_workflow_manage.py convention (SessionContext does NOT accept model/provider kwargs)"

patterns-established:
  - "Pattern: _save_locked reentrancy helper — cloned by any future filelocked JSON store that also needs to mutate under a held lock"
  - "Pattern: lazy-prune-at-read for TTL'd JSON store fields — no background pruner needed when reads are on-demand and infrequent"
  - "Pattern: disjoint-subkey additive edits to shared config/builder files for Wave parallelism"

requirements-completed: [BHV-03, BHV-04]

# Metrics
duration: 7min
completed: 2026-04-10
---

# Phase 10 Plan 03: Behavior Layer Read Side Summary

**PatternStore filelocked JSON store + SuggestAutomationTool with find_spec-based deploy detection, dismiss shortcut, and lazy 90-day suppression pruning — BHV-03/BHV-04 read-side contract fully shipped and wired through AppContext for Plan 10-04.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-10T21:55:40Z
- **Completed:** 2026-04-10T22:02:46Z
- **Tasks:** 7 (Task 0 through Task 6)
- **Files created:** 5 (2 source + 2 test + 1 deferred-items log)
- **Files modified:** 3 (settings.py, builder.py, registry_factory.py)
- **Tests added:** 19 (11 PatternStore + 8 SuggestAutomationTool)

## Accomplishments

- **PatternStore** implemented at `yigthinker/memory/patterns.py` (204 lines) with `load`, `save`, `_save_locked`, `suppress`, `list_patterns`, `list_active`, `_prune_expired_suppressions`. Atomic writes via `tempfile.mkstemp + os.replace` under `filelock.FileLock` — same shape as `WorkflowRegistry.save_index`.
- **CORR-04a lazy suppression pruning** proven by `test_lazy_prune_expired_suppression`: expired entries (suppressed_until < now) are cleared at read time inside the existing lock, then persisted. No background sweeper.
- **Pitfall 5 FileLock reentrancy** mitigated via `_save_locked` helper that writes without re-acquiring the lock. Proven by `test_save_locked_helper_exists_for_reentrancy` (inspects source for absence of `with self._lock:` inside the helper) and `test_suppress_then_save_roundtrip_no_deadlock`.
- **SuggestAutomationTool** implemented at `yigthinker/tools/workflow/suggest_automation.py` (170 lines) with D-21 output shape (sorted by `time_saved * frequency` descending) and D-22 dismiss shortcut returning `{dismissed, ok}` without listing.
- **`can_deploy_to` via `importlib.util.find_spec`** — the MCP packages `yigthinker_mcp_powerautomate` and `yigthinker_mcp_uipath` are NEVER imported. Proven by `test_can_deploy_to_via_findspec` which patches the `find_spec` call site and asserts no real import happened.
- **`gates.behavior` feature gate** added to `DEFAULT_SETTINGS['gates']` as a surgical one-line edit. Plan 10-04 will read the same gate for BHV-01/BHV-02 wiring.
- **Builder wiring** — `AppContext.pattern_store` field added, `PatternStore` instantiated inside `build_app` gated on `gate('behavior', settings=settings)`, threaded through `build_tool_registry(pattern_store=pattern_store)`.
- **Registry factory registration** — `SuggestAutomationTool` joins `WorkflowGenerateTool`, `WorkflowDeployTool`, `WorkflowManageTool` under the same `workflow` feature gate, guarded by `if pattern_store is not None` so it only activates when BOTH gates resolve.

## Task Commits

Each task was committed atomically (with `--no-verify` per parallel-executor policy):

1. **Task 0: RED-phase test stubs** — `d94b4a4` (test)
2. **Task 1: PatternStore implementation** — `d57b1c1` (feat)
3. **Task 2: SuggestAutomationTool implementation** — `9a27d7b` (feat)
4. **Task 3: gates.behavior feature gate** — `a58f630` (chore)
5. **Task 4: Builder.py PatternStore wiring** — `3bdf796` (feat)
6. **Task 5: registry_factory tool registration** — `9fd51e8` (feat)
7. **Task 6: Full-suite regression + smoke test** — no code commit (verification only)

## Files Created/Modified

### Created

- **`yigthinker/memory/patterns.py`** (204 lines) — `PatternStore` class with atomic-write JSON store, filelock, `_save_locked` reentrancy helper, lazy suppression pruning
- **`yigthinker/tools/workflow/suggest_automation.py`** (170 lines) — `SuggestAutomationTool` + `SuggestAutomationInput` Pydantic model; find_spec-based deploy target detection; dismiss shortcut
- **`tests/test_memory/test_patterns.py`** (11 tests) — full BHV-04 coverage: load_empty, save_atomic, suppress_90d_default, suppress_90d_expiry, suppress_missing_returns_false, list_active_min_frequency, list_active_default_hides_suppressed, list_active_include_suppressed_true, lazy_prune_expired, _save_locked_helper_exists_for_reentrancy, suppress_then_save_roundtrip_no_deadlock
- **`tests/test_tools/test_suggest_automation.py`** (8 tests) — full BHV-03/BHV-04 tool coverage: output_shape, filter_min_frequency, can_deploy_to_via_findspec, dismiss_writes_suppressed_until, dismiss_missing_pattern_returns_ok_false, filter_suppressed_default, include_suppressed_true, empty_store_returns_empty_suggestions
- **`.planning/phases/10-gateway-rpa-behavior/deferred-items.md`** — logs the out-of-scope `test_checkpoint_posts_to_callback_endpoint` failure owned by 10-01's pending CORR-01 template update

### Modified

- **`yigthinker/settings.py`** — single surgical edit: added `"behavior": True` inside `DEFAULT_SETTINGS['gates']`. Disjoint from 10-01's `DEFAULT_SETTINGS['gateway']['rpa']` and top-level `DEFAULT_SETTINGS['behavior']` keys (additive merge held cleanly).
- **`yigthinker/builder.py`** — 3 surgical edits: `AppContext.pattern_store` field, `build_app` PatternStore instantiation block, `AppContext()` return kwarg. 10-01's `rpa_state` + `workflow_registry` fields merged alongside without conflict.
- **`yigthinker/registry_factory.py`** — 3 surgical edits: `build_tool_registry(pattern_store=None)` kwarg, `_register_workflow_tools(pattern_store=None)` kwarg + lazy import + registration inside `if pattern_store is not None` guard, call site updated to thread `pattern_store=pattern_store`.

## Decisions Made

- **Lazy suppression pruning under the existing lock (CORR-04a enforcement)** — the implementation follows CORR-04a exactly: `list_patterns(prune=True)` / `list_active()` acquire the lock once, call `_prune_expired_suppressions(data)` (pure in-memory mutator), and persist via `_save_locked(data)` only if anything changed. No background pruner, no cron job, no scheduled task.
- **`_save_locked` reentrancy helper** — cloned from the WorkflowRegistry pattern idea with one deviation: the WorkflowRegistry doesn't need it because its only mutator (`save_index`) never calls itself. `PatternStore.suppress` and `PatternStore.list_patterns` both need to mutate under a held lock, so the helper is mandatory.
- **Test helper uses zero-arg `SessionContext()`** — the plan's example code constructed `SessionContext(session_id=..., model=..., provider=..., settings=...)`, but reading `yigthinker/session.py` confirmed `SessionContext` does NOT accept `model` or `provider` kwargs. Matched `tests/test_tools/test_workflow_manage.py`'s `SessionContext()` convention instead.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test helper SessionContext signature mismatch**
- **Found during:** Task 0 (RED-phase test stub creation)
- **Issue:** The plan's example code for `_make_ctx()` in `test_suggest_automation.py` used `SessionContext(session_id="test-session", model="test-model", provider=None, settings={})`. But `yigthinker/session.py` defines `SessionContext` as a dataclass with fields `session_id`, `settings`, `transcript_path`, `created_at`, `last_active`, `channel_origin`, `owner_id`, `vars`, `context_manager`, `stats`, `messages`, `subagent_manager` — no `model` or `provider` fields. Attempting to instantiate with those kwargs would crash at collection time or test runtime.
- **Fix:** Replaced the example with zero-arg `SessionContext()` (matching `tests/test_tools/test_workflow_manage.py`'s convention). Added a comment explaining the tool never reads `ctx.vars` so any valid SessionContext suffices.
- **Files modified:** `tests/test_tools/test_suggest_automation.py` (only the `_make_ctx` helper)
- **Verification:** `pytest --collect-only` succeeds (19 tests collected); all 8 `test_suggest_automation.py` tests pass GREEN after Task 2.
- **Committed in:** `d94b4a4` (Task 0 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — test helper signature correction to match actual SessionContext dataclass)
**Impact on plan:** Cosmetic — the tool contract was unaffected; the correction was purely in the test helper constructor. No scope creep.

## Issues Encountered

### 1. `test_checkpoint_posts_to_callback_endpoint` full-suite failure (out of scope)

- **Where:** `tests/test_tools/test_workflow_generate.py::test_checkpoint_posts_to_callback_endpoint`
- **Context:** Task 6 full-suite regression ran all tests except the 3 explicit-skip 10-01 stub files. One test in `test_workflow_generate.py` failed: it asserts the rendered `checkpoint_utils.py` contains `/api/rpa/callback`, but the current `checkpoint_utils.py.j2` template still emits `/api/rpa/heal` (the legacy Phase 8 shape).
- **Root cause:** This test was added by Plan 10-01 commit `e0417f4` (10-01's RED-phase test stub batch) as a regression guard for CORR-01. The fix — updating `yigthinker/tools/workflow/templates/base/checkpoint_utils.py.j2` to POST to `/api/rpa/callback` with the D-08 body shape — is 10-01's task, not mine.
- **Scope boundary:** Plan 10-03 owns `yigthinker/memory/patterns.py`, `yigthinker/tools/workflow/suggest_automation.py`, `yigthinker/registry_factory.py`, `yigthinker/settings.py` (gates.behavior only), `yigthinker/builder.py` (pattern_store field only). It does NOT own the checkpoint template.
- **Resolution:** Logged to `.planning/phases/10-gateway-rpa-behavior/deferred-items.md`. Will resolve automatically when 10-01 completes its CORR-01 task. Not a blocker for 10-03 completion.
- **Evidence:** `git log --oneline` shows 10-01's last commit is `feat(10-01): add RPAController with stubbed callback + full report path` (`370183a`) — the template update is still pending in 10-01's plan.

### 2. 10-01 RED-phase test collection errors (expected, out of scope)

- **Where:** `tests/test_gateway/test_rpa_endpoints.py`, `tests/test_gateway/test_rpa_controller.py`, `tests/test_gateway/test_rpa_state.py`
- **Context:** These are RED-phase test stubs added by 10-01 commit `e0417f4`. They import modules like `yigthinker.gateway.rpa_controller` which 10-01 has not yet fully landed.
- **Resolution:** Ignored via `--ignore=` flags during full-suite run. Expected for Wave 1 parallel execution per the plan's own statement: "If 10-01 has NOT yet been committed at the time 10-03 runs its regression, some 10-01-owned test files will simply not exist yet — pytest will treat them as ... not fail." Mine are worse (collection errors rather than missing files) but the intent is the same.

## Known Stubs

**`~/.yigthinker/patterns.json` is EMPTY at the end of 10-03.** This is by design:

- Plan 10-03 ships the complete READ side of BHV-03/BHV-04 (the `PatternStore` + `SuggestAutomationTool` + wiring).
- Plan 10-04 (Wave 2) ships the WRITE side — extending the AutoDream prompt to emit `candidate_patterns` that flow into `PatternStore.save(...)`.
- Until 10-04 lands, calling `suggest_automation` returns `{"suggestions": [], "summary": "No automation opportunities detected yet."}` — the friendly empty-state path proven by `test_empty_store_returns_empty_suggestions`.
- This is NOT a stub in the "placeholder that must be fixed" sense — it's the intended Wave 1 handoff to Wave 2. The LLM will see "no opportunities detected yet" and fall back to suggesting the user run more sessions until AutoDream has enough cross-session data to detect a pattern.

No stub components exist in the code itself. No hardcoded empty returns. No placeholder text that will surface to end users without resolution.

## User Setup Required

None - no external service configuration required for Plan 10-03. The behavior subsystem activates automatically when `DEFAULT_SETTINGS['gates']['behavior']` is True (the default).

## Next Phase Readiness

### Ready for Plan 10-04 (Wave 2)

- `AppContext.pattern_store` is wired and non-None when the `behavior` gate is on. Plan 10-04 can `ctx.pattern_store.save(patterns_dict)` directly from an extended AutoDream consolidation path.
- `gates.behavior` exists as a single toggle — 10-04 can gate the BHV-01 system prompt directive and BHV-02 startup alert provider on the same check: `gate('behavior', settings=settings)`.
- `SuggestAutomationTool` is already registered under `workflow` when `pattern_store is not None`, so the BHV-01 directive can reference it by name (`suggest_automation`) immediately.
- `test_empty_store_returns_empty_suggestions` establishes the friendly empty-state behavior Plan 10-04 does NOT need to worry about — calling `suggest_automation` pre-AutoDream-write is safe.

### Blockers for downstream work

- **CORR-01 template update** — Plan 10-01 still needs to ship the `checkpoint_utils.py.j2` update. Until then, the `test_checkpoint_posts_to_callback_endpoint` regression will stay red. Not my problem.
- **AutoDream prompt extension** — D-17, CORR-04c. This is 10-04's responsibility.

## Self-Check: PASSED

**Files verified to exist on disk:**
- `yigthinker/memory/patterns.py` — FOUND (204 lines)
- `yigthinker/tools/workflow/suggest_automation.py` — FOUND (170 lines)
- `tests/test_memory/test_patterns.py` — FOUND (11 tests)
- `tests/test_tools/test_suggest_automation.py` — FOUND (8 tests)
- `.planning/phases/10-gateway-rpa-behavior/deferred-items.md` — FOUND

**Commits verified to exist in git log:**
- `d94b4a4` — test(10-03): add RED-phase tests for PatternStore and SuggestAutomationTool — FOUND
- `d57b1c1` — feat(10-03): implement PatternStore with atomic writes and lazy suppression pruning — FOUND
- `9a27d7b` — feat(10-03): implement SuggestAutomationTool with find_spec-based deploy detection — FOUND
- `a58f630` — chore(10-03): add behavior feature gate to DEFAULT_SETTINGS — FOUND
- `3bdf796` — feat(10-03): thread PatternStore through builder.py and AppContext — FOUND
- `9fd51e8` — feat(10-03): register SuggestAutomationTool under workflow gate — FOUND

**Test verification:**
- `pytest tests/test_memory/test_patterns.py tests/test_tools/test_suggest_automation.py -x --tb=short` — 19 passed, 0 failed
- `pytest tests/test_tools/test_registry_factory.py tests/test_tools/test_registry_factory_phase3.py -x --tb=short` — 7 passed, 0 failed (no regression from Task 5 kwargs addition)
- End-to-end smoke test (save → list → dismiss → empty list) — all 4 assertions passed

**Acceptance criteria audit:**
- CORR-04a lazy suppression pruning — PROVEN by `test_lazy_prune_expired_suppression`
- Pitfall 5 FileLock reentrancy — PROVEN by `test_save_locked_helper_exists_for_reentrancy` and `test_suppress_then_save_roundtrip_no_deadlock`
- `can_deploy_to` via find_spec (no import) — PROVEN by `test_can_deploy_to_via_findspec` (patches `importlib.util.find_spec` and asserts no real MCP package import)
- Dismiss shortcut — PROVEN by `test_dismiss_writes_suppressed_until` and `test_dismiss_missing_pattern_returns_ok_false`
- File does NOT contain `import mcp` — PROVEN by manual grep assertion in Task 2 verification step

---
*Phase: 10-gateway-rpa-behavior*
*Plan: 03 (Wave 1, parallel with 10-01)*
*Completed: 2026-04-10*
