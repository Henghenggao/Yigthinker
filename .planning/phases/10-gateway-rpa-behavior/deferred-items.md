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
