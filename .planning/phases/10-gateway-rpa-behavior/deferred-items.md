# Deferred Items — Phase 10 (gateway-rpa-behavior)

Out-of-scope issues encountered during plan execution that are either owned
by another plan in the same phase or represent pre-existing failures unrelated
to the current plan's scope.

## From Plan 10-03 (Wave 1, parallel with 10-01)

### 1. test_checkpoint_posts_to_callback_endpoint fails (CORR-01 pending)

- **File:** `tests/test_tools/test_workflow_generate.py::test_checkpoint_posts_to_callback_endpoint`
- **Observed during:** Plan 10-03 Task 6 full-suite regression (2026-04-10)
- **Symptom:** Assertion `"/api/rpa/callback" in text` fails — rendered
  `checkpoint_utils.py` still contains the legacy `/api/rpa/heal` endpoint
  and legacy `{workflow, checkpoint, error, context}` payload shape.
- **Root cause:** 10-01 has not yet landed the CORR-01 template update to
  `yigthinker/tools/workflow/templates/base/checkpoint_utils.py.j2`. The
  test was added by 10-01's test stub batch (commit `e0417f4`) as a
  RED-phase regression guard for 10-01's own task.
- **Ownership:** Plan 10-01 (CORR-01 — template update to POST to
  `/api/rpa/callback` with the D-08 body shape and fresh UUID4 `callback_id`).
- **Scope boundary:** Out of scope for Plan 10-03. My plan touches
  `yigthinker/memory/patterns.py`, `yigthinker/tools/workflow/suggest_automation.py`,
  `yigthinker/registry_factory.py`, `yigthinker/settings.py` (gates.behavior only),
  and `yigthinker/builder.py` (pattern_store field only). It does NOT touch
  `checkpoint_utils.py.j2`.
- **Resolution:** Will turn green when 10-01 completes its CORR-01 task.
- **Status (2026-04-11):** RESOLVED by Plan 10-01 commit `9d8d89f` — test now
  passes in the full suite.

## From Plan 10-01 (Wave 1, parallel with 10-03)

### 1. test_list_sessions_excludes_old_files flaky on Windows NTFS

- **File:** `tests/test_memory/test_auto_dream.py::test_list_sessions_excludes_old_files`
- **Observed during:** Plan 10-01 Task 5 full-suite regression (2026-04-11)
- **Symptom:** Assertion `"old.jsonl" not in names` fails when the test runs
  inside the full suite; the `old.jsonl` file created before `DreamState.update()`
  still shows up as newer-than-last-dream because the NTFS file mtime
  granularity (~15 ms on some FAT/NTFS volumes) is larger than the test's
  10 ms `time.sleep(0.01)` gap.
- **Root cause:** Pre-existing filesystem timing race; the test was added
  in commit `3887578` (Plan 05-01) and has never been updated. Unrelated to
  `yigthinker/gateway/*` or `yigthinker/tools/workflow/*`.
- **Evidence it's pre-existing:** Last touched by commit `3887578`
  (2025-era), no Plan 10-01 file is in scope of this test. Test passes
  reliably in isolation (`pytest tests/test_memory/test_auto_dream.py::test_list_sessions_excludes_old_files`)
  but races only under the full-suite load.
- **Scope boundary:** Out of scope for Plan 10-01. My plan touches
  `yigthinker/gateway/rpa_state.py`, `yigthinker/gateway/rpa_controller.py`,
  `yigthinker/gateway/server.py`, `yigthinker/tools/workflow/templates/base/checkpoint_utils.py.j2`,
  `yigthinker/tools/workflow/templates/base/main.py.j2`,
  `yigthinker/tools/workflow/workflow_generate.py`, and additive edits to
  `yigthinker/settings.py` and `yigthinker/builder.py`. None of these
  touch session memory or AutoDream.
- **Resolution:** Deferred to future memory-subsystem maintenance plan.
  Suggested fix: increase `time.sleep(0.01)` to `time.sleep(0.05)` or
  use explicit mtime stamping via `os.utime()` rather than relying on
  filesystem mtime granularity.

## From Plan 10-02 (Wave 2, parallel with 10-04)

### 1. 10-04 in-flight RED tests failing in full suite

- **Files:**
  - `tests/test_agent_memory.py::test_session_start_injects_health_alerts`
  - `tests/test_agent_memory.py::test_session_start_silent_empty_registry`
  - `tests/test_agent_memory.py::test_session_start_silent_healthy`
  - `tests/test_agent_memory.py::test_session_start_resilient_bad_registry`
  - `tests/test_memory/test_auto_dream.py::test_prompt_includes_pattern_section`
  - `tests/test_memory/test_auto_dream.py::test_candidate_patterns_persisted`
  - `tests/test_memory/test_auto_dream.py::test_candidate_patterns_parse_failure`
- **Observed during:** Plan 10-02 Task 3 full-suite regression (2026-04-11)
- **Symptoms:**
  - `AttributeError: 'AgentLoop' object has no attribute 'set_startup_alert_provider'`
  - `AssertionError: 'CANDIDATE_PATTERNS' in prompt` — pattern section not yet appended
  - `TypeError: AutoDream.__init__() got an unexpected keyword argument 'pattern_store'`
- **Root cause:** These tests were added in commit `3e4043a`
  (`test(10-04): add BHV-01/02/05 tests to existing test files (RED)`) —
  Plan 10-04's intentional RED phase. They expect code that 10-04 is
  concurrently implementing in `yigthinker/agent.py`, `yigthinker/memory/auto_dream.py`,
  and `yigthinker/builder.py`. The executor running 10-04 will turn them green.
- **Ownership:** Plan 10-04 (Behavior Layer: BHV-01 prompt directive,
  BHV-02 startup alert provider via CORR-02, BHV-05 cross-session pattern
  detector via CORR-04c).
- **Scope boundary:** Out of scope for Plan 10-02. My plan touches
  `yigthinker/gateway/extraction_prompt.py` (new),
  `yigthinker/gateway/rpa_controller.py` (replace `_extract_decision_stub`),
  and `tests/test_gateway/test_rpa_controller.py` (extension). Zero file
  overlap with 10-04.
- **Resolution:** Will turn green when 10-04 completes its Task 1-3
  (set_startup_alert_provider setter + AutoDream pattern_store kwarg +
  CANDIDATE_PATTERNS prompt section).

### 2. test_list_sessions_excludes_old_files still flaky

- **File:** `tests/test_memory/test_auto_dream.py::test_list_sessions_excludes_old_files`
- Same pre-existing Windows NTFS flake documented above under Plan 10-01.
  Out of scope for 10-02 (no session memory / AutoDream files touched).
