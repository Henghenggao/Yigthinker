---
phase: 10-gateway-rpa-behavior
plan: 04
subsystem: behavior-layer
tags: [agent-loop, context-manager, auto-dream, pattern-store, startup-alert, corr-02, corr-04c, bhv-01, bhv-02, bhv-05]

# Dependency graph
requires:
  - phase: 10-01
    provides: behavior.health_check_threshold + suggest_automation settings skeleton, AppContext.workflow_registry field, WorkflowManageTool lifecycle + _health_check (unchanged, reused)
  - phase: 10-03
    provides: PatternStore class (load/save/suppress), AppContext.pattern_store field, gates.behavior gate flag
  - phase: 05-session-memory-auto-dream
    provides: AutoDream skeleton + DREAM_PROMPT constant that 10-04 extends at the call site (NOT at constant) per CORR-04c
  - phase: 09-deployment-lifecycle
    provides: WorkflowManageTool._health_check (ctx-free, reusable from startup alert closure)
provides:
  - ContextManager.build_automation_directive (BHV-01 / D-23 / D-24 directive renderer)
  - AgentLoop._startup_alert_provider field + set_startup_alert_provider setter (CORR-02 replaces D-14 SessionStart-hook design)
  - AgentLoop.run() system_prompt assembly extended: automation directive appended every iteration, startup alert prepended exactly once on iteration==1 with defensive try/except (Pitfall 3 outer defense)
  - AutoDream.__init__ pattern_store kwarg (optional, default None — Phase 5 regression safe)
  - _CANDIDATE_PATTERNS_MARKER + _CANDIDATE_PATTERNS_EXTENSION module constants in auto_dream.py
  - _consolidate_via_llm call-site prompt extension (NOT DREAM_PROMPT edit — CORR-04c guarantee)
  - AutoDream._merge_candidate_patterns helper: normalizes candidate entries, preserves existing suppression state, unions sessions
  - builder.py pass-through wiring: AutoDream(pattern_store=pattern_store) + startup_alert_provider closure over WorkflowManageTool._health_check with alert_on_overdue + alert_on_failure_rate_pct thresholds
affects: [Phase 11, Phase 12, future behavior-layer enhancements]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CORR-02 callback-not-hook pattern: AgentLoop exposes a set_startup_alert_provider(fn) setter; builder.py wires a closure that reads workflow registry via WorkflowManageTool._health_check and returns a formatted alert string or None. AgentLoop.run calls it exactly once per run gated on iteration==1. No SessionStart hook — HookResult has no context-injection variant."
    - "Double-defense try/except on provider invocations (Pitfall 3): closure body catches all exceptions internally AND AgentLoop.run wraps the call at the call site. A crashing registry/closure never breaks a session."
    - "CORR-04c call-site prompt extension: _CANDIDATE_PATTERNS_EXTENSION is appended to the local prompt variable inside _consolidate_via_llm instead of mutating the module-level DREAM_PROMPT constant. This preserves every Phase 5 unit test that asserts on the original prompt shape (test_dream_consolidation_calls_llm, test_dream_prunes_when_over_4k, test_dream_reads_session_memories)."
    - "str.partition(marker) splitting for LLM response parsing: pre-marker text is the memory markdown (regression-safe), post-marker blob is defensively JSON-parsed and merged into PatternStore. Malformed JSON is silently suppressed via outer try/except in the caller — memory write still succeeds."
    - "Disjoint-additive edits on top of Wave 1: 10-01 added rpa_state + workflow_registry to AppContext, 10-03 added pattern_store + gates.behavior, 10-04 adds the final wiring layer on top without touching anything those waves claimed."
    - "Defaulting AutoDream.__init__(pattern_store=None) so the existing Phase 5 test sites that call AutoDream() without a kwarg continue to work unchanged (Phase 5 regression guard)."

key-files:
  created: []
  modified:
    - yigthinker/context_manager.py
    - yigthinker/agent.py
    - yigthinker/memory/auto_dream.py
    - yigthinker/builder.py
    - tests/test_context_manager.py
    - tests/test_agent_memory.py
    - tests/test_memory/test_auto_dream.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "CORR-02: BHV-02 is a startup alert provider callback (not a SessionStart hook) because HookResult supports only ALLOW/WARN/BLOCK — no context-injection variant exists. Wired via AgentLoop.set_startup_alert_provider from builder.py; called exactly once per run at iteration==1 from inside the system_prompt assembly block."
  - "CORR-04c: The CANDIDATE_PATTERNS: instruction block is appended to the local prompt variable inside _consolidate_via_llm rather than edited into the DREAM_PROMPT constant. Phase 5's existing 11 auto_dream tests keep passing byte-identically including test_dream_consolidation_calls_llm, test_dream_prunes_when_over_4k, and test_dream_reads_session_memories."
  - "D-23 directive text is copied verbatim from CONTEXT.md (no paraphrasing). build_automation_directive is a pure renderer gated on settings.behavior.suggest_automation.enabled (D-24, default True) so old settings.json users get the directive automatically."
  - "Pitfall 3 double defense: the startup_alert_provider closure in builder.py catches Exception internally AND AgentLoop.run wraps the call at the call site. A crashing registry (corrupted registry.json, missing croniter, etc.) never breaks AgentLoop.run."
  - "AutoDream.__init__ pattern_store kwarg defaults to None (trailing keyword-only). Existing bare AutoDream() construction sites in Phase 5 tests continue to work unchanged — no test rewrite needed."
  - "_merge_candidate_patterns preserves existing suppression state when merging: if a pattern_id already exists, its suppressed/suppressed_until fields are carried over from the prior entry and sessions are union-merged. This ensures cross-session pattern detection cannot accidentally unsuppress a user-suppressed pattern via an LLM re-emit."
  - "_consolidate_via_llm returns the pre-marker portion via str.partition, rstripped, so the regression test asserting 'consolidated' in memory_path content still passes when the LLM response has no marker (partition returns the full text as the first element)."

patterns-established:
  - "Callback-not-hook for cross-run context injection: when a system prompt addendum depends on runtime state (registry status, health checks, counters), wire a closure via a setter on AgentLoop instead of a SessionStart hook. Hooks have no context-injection return type."
  - "Call-site prompt extension: when extending an LLM prompt owned by an existing consolidation routine, append to the local variable at the call site rather than mutating the module-level constant — preserves test stability."
  - "Partition-and-merge LLM response parsing: split response on a fixed marker, write the pre-marker portion to the canonical output sink (memory markdown), and attempt structured parse + persist on the post-marker portion defensively."
  - "Trailing-optional kwarg additions: when extending a Phase-N class constructor, add new kwargs as trailing keyword-only parameters with sensible defaults so existing call sites and tests keep working without rewrites."

requirements-completed: [BHV-01, BHV-02, BHV-05]

# Metrics
duration: ~15min
completed: 2026-04-11
---

# Phase 10 Plan 04: Behavior Layer Wiring Summary

**BHV-01/02/05 wired end-to-end: ContextManager automation directive, AgentLoop startup_alert_provider callback (CORR-02) with first-iteration prepend + Pitfall-3 double defense, AutoDream CANDIDATE_PATTERNS call-site prompt extension (CORR-04c) + PatternStore merge, and builder.py closure over WorkflowManageTool._health_check — Phase 10 now feature-complete for `/gsd:verify-work`.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-11 (resume)
- **Completed:** 2026-04-11
- **Tasks:** 6 (5 auto + 1 verification-only)
- **Files modified:** 7 (4 source + 3 test)

## Accomplishments

- **BHV-01 directive** — `ContextManager.build_automation_directive(settings)` returns the verbatim D-23 text when `settings.behavior.suggest_automation.enabled` is True (default True), None otherwise. Called from `AgentLoop.run` inside the system_prompt assembly block and appended after subagent notifications.
- **BHV-02 startup alert provider (CORR-02)** — `AgentLoop._startup_alert_provider` field + `set_startup_alert_provider` setter. `AgentLoop.run` calls the provider exactly once per run at `iteration == 1`, wraps the call in try/except as outer defense, and prepends the returned alert text to `system_prompt` so the `[Workflow Health Alert]` block appears at the top. Provider closure in `builder.py` is gated on `gate('behavior')` AND `workflow_registry is not None`, catches all exceptions internally as inner defense, and formats a D-15 style multi-line alert when any workflow is overdue or has a failure rate above the threshold.
- **BHV-05 CANDIDATE_PATTERNS extension (CORR-04c)** — `AutoDream.__init__` gains optional `pattern_store` kwarg (default None). `_CANDIDATE_PATTERNS_EXTENSION` is a module constant appended to the prompt at the `_consolidate_via_llm` call site. The response is split on `CANDIDATE_PATTERNS:` — pre-marker portion goes to `memory_path.write_text` exactly as before, post-marker portion is JSON-parsed and merged into `PatternStore` via the new `_merge_candidate_patterns` helper. Malformed JSON is silently suppressed. `DREAM_PROMPT` constant is byte-identical to Phase 5.
- **builder.py wiring** — `AutoDream(pattern_store=pattern_store)` replaces the bare `AutoDream()` construction; a new `startup_alert_provider` closure is built over `WorkflowManageTool(registry=workflow_registry)._health_check` and wired via `agent.set_startup_alert_provider(...)`. Lazy import of `WorkflowManageTool` inside the block so missing jinja2/croniter still works.
- **10 new tests, 0 rewrites** — 2 BHV-01 tests + 4 BHV-02 tests + 4 BHV-05 tests appended to the three existing test files. Every pre-existing Phase 5 test (including `test_dream_consolidation_calls_llm` as the CORR-04c regression guard) passes byte-identically.

## Task Commits

1. **Task 0: RED-phase tests appended** — `3e4043a` (test)
2. **Task 1: ContextManager.build_automation_directive** — `a20d7b5` (feat)
3. **Task 2: AgentLoop startup_alert_provider + directive call** — `d77e5e9` (feat)
4. **Task 3: AutoDream CANDIDATE_PATTERNS extension** — `8c834f4` (feat)
5. **Task 4: builder.py alert provider closure + AutoDream kwarg** — `251e655` (feat)
6. **Task 5: Full-suite regression** — no code changes (verification only)

Task 0 was committed before the 10-02 parallel plan finished — 10-02's Task 3 full-suite run caught my RED tests and logged them in `.planning/phases/10-gateway-rpa-behavior/deferred-items.md` (section "From Plan 10-02 — 10-04 in-flight RED tests failing in full suite"). That deferred-items entry is now RESOLVED by Tasks 1-4 of this plan; every test listed is green.

## Files Created/Modified

**Modified source files:**
- `yigthinker/context_manager.py` — `build_automation_directive(settings)` method (27 lines appended)
- `yigthinker/agent.py` — `_startup_alert_provider` field + `set_startup_alert_provider` setter + system_prompt assembly block extended with BHV-01 directive append and BHV-02 alert prepend (47 lines added)
- `yigthinker/memory/auto_dream.py` — `pattern_store` kwarg on `__init__`, `_CANDIDATE_PATTERNS_MARKER` + `_CANDIDATE_PATTERNS_EXTENSION` constants, `_consolidate_via_llm` rewrite (append extension, partition response, defensive merge), `_merge_candidate_patterns` helper (128 lines added, 2 removed — DREAM_PROMPT untouched)
- `yigthinker/builder.py` — `AutoDream(pattern_store=pattern_store)` pass-through + new BHV-02 alert provider block (63 lines added)

**Modified test files:**
- `tests/test_context_manager.py` — +2 BHV-01 tests appended
- `tests/test_agent_memory.py` — +4 BHV-02 tests appended (reuses existing `_make_loop` helper)
- `tests/test_memory/test_auto_dream.py` — +4 BHV-05 tests appended (new `capture_chat` provider mock pattern, PatternStore integration)

**Modified planning docs:**
- `.planning/REQUIREMENTS.md` — BHV-01, BHV-02, BHV-05 marked complete in both the checkbox list and the traceability table

## Decisions Made

None beyond the CORR-02 / CORR-04c / D-23 / D-24 / D-15 decisions already locked in CONTEXT.md. Every edit is a literal materialization of the plan tasks; the only local judgement calls were on variable naming (`_thresholds`, `_workflow_manage`, `problems`), the closure-internal bullet-point character (used `*` instead of `•` to match ASCII-safe style in the rest of the codebase's print statements), and the defensive `rstrip()` on the memory_text after partition (so the trailing whitespace introduced by the extension append doesn't leak into the written MEMORY.md).

## Deviations from Plan

**None — plan executed exactly as written.**

Three minor style choices beneath the "deviation" threshold:
- Bullet character `*` instead of `•` in the alert closure's multi-line output (matches rest-of-codebase ASCII convention; the test asserts on `[Workflow Health Alert]` + `monthly_sales_report`, not on the bullet glyph).
- Used `getattr(ctx, "settings", None) or {}` in the `build_automation_directive` call site rather than `ctx.settings` directly — defensive against future SessionContext shape changes. SessionContext does have `settings: dict[str, Any] = field(default_factory=dict)` so the fallback is belt-and-suspenders.
- Wrapped the `build_automation_directive` call itself in try/except `directive = None` so a future regression in the directive renderer also cannot break `AgentLoop.run`. Not required by the plan but consistent with the Pitfall 3 defense-in-depth theme.

## Issues Encountered

**None.** All three subsystems wired cleanly on the first pass:

- Task 0 RED — all 10 new tests failed with the expected `AttributeError` / `TypeError` on missing attributes.
- Task 1 GREEN — `test_context_manager.py` 5/5 pass.
- Task 2 GREEN — `test_agent_memory.py` 10/10 pass; `test_context_manager.py` unchanged (5/5).
- Task 3 GREEN — `test_memory/test_auto_dream.py` 17/17 pass including the Phase 5 regression test `test_dream_consolidation_calls_llm` and the flaky Windows NTFS test `test_list_sessions_excludes_old_files` (the latter happened to pass in this run — it's a filesystem timing race, not a deterministic failure).
- Task 4 wiring — smoke test confirms all four end-to-end assertions: `has startup_alert_provider: True`, `pattern_store present: True`, `directive enabled: True`, `directive disabled: True`, `AutoDream default pattern_store: None`.
- Task 5 full-suite regression — **664 passed, 1 skipped, 0 failed** in 13.7s. The skip is the 10-01 Windows sqlite cross-TestClient teardown guard (`tests/test_gateway/test_rpa_endpoints.py:241`), not related to 10-04.

## Regression Guard Verification

Per the success criteria, I verified:

- `grep "set_startup_alert_provider" yigthinker/agent.py` returns 1 match (the setter definition).
- `grep "SessionStart" yigthinker/memory/auto_dream.py yigthinker/agent.py yigthinker/builder.py` — there is a `SessionStart` hook fired in `agent.py` line 76 (the existing Phase 5 hook for general session lifecycle events), but zero SessionStart hooks with health/alert wiring. `grep -i 'health\|alert'` on the SessionStart lines returns nothing. CORR-02 is preserved.
- `grep -n "^DREAM_PROMPT = " yigthinker/memory/auto_dream.py` shows line 14 with the constant unchanged; the 5-section structure (Data Source Knowledge / Business Rules & Patterns / Errors & Corrections / Key Findings / Analysis Log) is byte-identical to Phase 5. CORR-04c guard holds.
- Phase 5 test `test_dream_consolidation_calls_llm` passes without modification (CORR-04c regression guard).
- Phase 5 test `test_boundary_at_10_rows` passes without modification.
- `_make_loop` helper in `test_agent_memory.py` is unchanged; my 4 new BHV-02 tests reuse it verbatim.

## Parallel Wave Coordination

This plan ran in parallel with 10-02 (RPA extraction LLM path). Files were strictly disjoint:
- **10-02 owned:** `yigthinker/gateway/extraction_prompt.py` (new), `yigthinker/gateway/rpa_controller.py` (_extract_decision_stub replacement), `tests/test_gateway/test_rpa_controller.py`.
- **10-04 owned:** `yigthinker/context_manager.py`, `yigthinker/agent.py`, `yigthinker/memory/auto_dream.py`, `yigthinker/builder.py` (additive on top of 10-01 + 10-03 without touching their subkeys), and 3 test files.
- **Zero overlap, zero merge conflicts.** 10-02's deferred-items entry ("10-04 in-flight RED tests failing in full suite") caught my Task 0 RED commit and is now fully RESOLVED.

## Next Phase Readiness

**Phase 10 is feature-complete for `/gsd:verify-work`.** All five behavior-layer requirements (BHV-01 through BHV-05) plus all four gateway-RPA requirements (GW-RPA-01 through GW-RPA-04) plus the CORR-01 template update are now green in the full suite (664 passed).

End-to-end contract observable without any LLM or Gateway dependency:
- CLI/REPL session: BHV-01 directive renders into system_prompt on every iteration when `behavior.suggest_automation.enabled = True`.
- Gateway session with workflow_registry: BHV-02 startup alert prepends to system_prompt on iteration 1 when any workflow is overdue or has failure_rate_pct >= threshold.
- Background AutoDream pass: BHV-05 CANDIDATE_PATTERNS extension nudges the LLM to emit a JSON block that flows through `_merge_candidate_patterns` into PatternStore with merged suppression state.
- BHV-03 `suggest_automation` tool (already landed in 10-03) reads the patterns 10-04 wrote and serves them to the LLM.
- BHV-04 suppression state (already wired in 10-03 PatternStore) is preserved by `_merge_candidate_patterns`.

**Ready for:** `/gsd:verify-work` to confirm the full Phase 10 contract. After verification, Phase 11 (UiPath MCP) and Phase 12 (Power Automate MCP) can proceed independently — neither depends structurally on Phase 10.

## Self-Check: PASSED

**Created files:** None (all 10-04 work is additive edits to existing files).

**Modified files — all present:**
- `yigthinker/context_manager.py` — FOUND (grep `build_automation_directive` → 2 matches: method def + docstring reference)
- `yigthinker/agent.py` — FOUND (grep `set_startup_alert_provider` → 1 match at line 66)
- `yigthinker/memory/auto_dream.py` — FOUND (grep `_CANDIDATE_PATTERNS_MARKER` → 3 matches)
- `yigthinker/builder.py` — FOUND (grep `agent.set_startup_alert_provider` → 1 match)
- `tests/test_context_manager.py` — FOUND (5 tests collected)
- `tests/test_agent_memory.py` — FOUND (10 tests collected)
- `tests/test_memory/test_auto_dream.py` — FOUND (17 tests collected)

**Commits — all present in git log:**
- `3e4043a` test(10-04): add BHV-01/02/05 tests to existing test files (RED) — FOUND
- `a20d7b5` feat(10-04): ContextManager.build_automation_directive for BHV-01 — FOUND
- `d77e5e9` feat(10-04): AgentLoop startup_alert_provider + automation directive — FOUND
- `8c834f4` feat(10-04): AutoDream BHV-05 CANDIDATE_PATTERNS extension (CORR-04c) — FOUND
- `251e655` feat(10-04): wire BHV-02 alert provider + BHV-05 pattern store in builder — FOUND

**Pytest final state:** 664 passed, 1 skipped (10-01 Windows sqlite guard), 0 failed.

---
*Phase: 10-gateway-rpa-behavior*
*Completed: 2026-04-11*
