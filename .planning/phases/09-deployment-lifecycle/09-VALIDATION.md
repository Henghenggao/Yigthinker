---
phase: 9
slug: deployment-lifecycle
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
updated: 2026-04-11
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` (asyncio_mode = "auto") |
| **Quick run command** | `python -m pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_manage.py tests/test_tools/test_workflow_templates.py tests/test_tools/test_registry_factory.py -x -q` |
| **Full suite command** | `python -m pytest -x -q` |
| **Estimated runtime** | Quick: ~1s, Full: ~15s |

---

## Sampling Rate

- **After every task commit:** Run the task-specific test file (e.g., `pytest tests/test_tools/test_workflow_deploy.py -x -q`)
- **After every plan wave:** Run the full quick command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Test File | Key Tests | Status |
|---------|------|------|-------------|-----------|-----------|-----------|--------|
| 09-01-01 | 01 | 1 | DEP-05 | unit | `tests/test_tools/test_workflow_registry.py` | `test_lazy_defaults_on_read`, `test_lazy_defaults_do_not_swallow_corruption`, `test_extended_fields_write_through` | ✅ green |
| 09-01-02 | 01 | 1 | DEP-01 | unit | `tests/test_tools/test_workflow_templates.py` | `test_render_text_skips_ast`, `test_render_text_runs_credential_scanner` | ✅ green |
| 09-01-03 | 01 | 1 | DEP-01 | unit | `tests/test_tools/test_workflow_templates.py` | `test_local_scheduler_templates` | ✅ green |
| 09-01-04 | 01 | 1 | DEP-01, DEP-05 | unit+integration | `tests/test_tools/test_workflow_deploy.py` | `test_local_mode`, `test_task_scheduler_xml_shape`, `test_crontab_txt_shape`, `test_cron_to_taskscheduler`, `test_invalid_target_mode_combo`, `test_invalid_schedule_fails_fast`, `test_deploy_writes_registry_metadata`, `test_deploy_writes_manifest_metadata` | ✅ green |
| 09-01-05 | 01 | 1 | DEP-01 | unit | `tests/test_tools/test_registry_factory.py` | `test_workflow_deploy_registered` | ✅ green |
| 09-02-01 | 02 | 2 | DEP-02 | unit | `tests/test_tools/test_workflow_templates.py` | `TestPABundleTemplates::test_workflow_json_shape`, `TestPABundleTemplates::test_api_properties_shape`, `TestPABundleTemplates::test_definition_has_recurrence_trigger`, `TestPABundleTemplates::test_guided_pa_bundle` | ✅ green |
| 09-02-02 | 02 | 2 | DEP-02 | unit | `tests/test_tools/test_workflow_templates.py` | `TestUiPathBundleTemplates::test_project_json_shape`, `TestUiPathBundleTemplates::test_main_xaml_is_valid_xml`, `TestUiPathBundleTemplates::test_uipath_reference_fixture_parses`, `TestUiPathBundleTemplates::test_guided_uipath_bundle`, `TestUiPathBundleTemplates::test_flow_import_zip_structure` | ✅ green |
| 09-02-03 | 02 | 2 | DEP-02, DEP-05 | integration | `tests/test_tools/test_workflow_deploy.py` | `TestWorkflowDeployGuided::test_guided_mode_power_automate`, `test_guided_mode_uipath`, `test_guided_updates_registry_metadata`, `test_guided_mode_local_target_rejected` | ✅ green |
| 09-02-04 | 02 | 2 | DEP-03, DEP-04, DEP-05 | unit | `tests/test_tools/test_workflow_deploy.py` | `TestWorkflowDeployAuto::test_auto_mode`, `test_auto_mode_returns_next_steps`, `test_auto_mode_mcp_missing_error`, `test_auto_mode_local_target_rejected` | ✅ green |
| 09-03-01 | 03 | 2 | LCM-01, LCM-02 | unit | `tests/test_tools/test_workflow_manage.py` | `TestWorkflowManageList::test_list_and_inspect`, `test_list_hides_retired_by_default`, `test_list_includes_retired_when_flag_set`, `test_inspect_unknown_workflow_errors` | ✅ green |
| 09-03-02 | 03 | 2 | LCM-03 | unit | `tests/test_tools/test_workflow_manage.py` | `TestWorkflowManagePause::test_pause_resume`, `test_pause_returns_next_step_local`, `test_pause_returns_next_step_power_automate`, `test_pause_requires_workflow_name` | ✅ green |
| 09-03-03 | 03 | 2 | LCM-04 | unit | `tests/test_tools/test_workflow_manage.py` | `TestWorkflowManageRollback::test_rollback`, `test_rollback_requires_target_version`, `test_rollback_unknown_target_version_errors`, `test_rollback_same_version_is_noop_or_errors` | ✅ green |
| 09-03-04 | 03 | 2 | LCM-05 | unit | `tests/test_tools/test_workflow_manage.py` | `TestWorkflowManageRetire::test_retire`, `test_retire_hides_from_list`, `test_retire_unknown_workflow_errors` | ✅ green |
| 09-03-05 | 03 | 2 | LCM-06 | unit | `tests/test_tools/test_workflow_manage.py` | `TestWorkflowManageHealthCheck::test_health_check_with_empty_data`, `test_health_check_overdue`, `test_health_check_skips_paused_for_overdue`, `test_health_check_failure_rate_computed_when_run_count_positive` | ✅ green |
| 09-03-06 | 03 | 2 | LCM-01..06 | registration | `tests/test_tools/test_registry_factory.py` | `TestWorkflowManageRegistration::test_workflow_manage_registered_when_gate_enabled`, `test_workflow_manage_not_registered_when_gate_disabled` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All Wave 0 artifacts landed. Test files were added following the Phase 8 flat convention under `tests/test_tools/`.

**Plan 09-01 Wave 0:**
- [x] `tests/test_tools/test_workflow_deploy.py` — DEP-01 tests
- [x] Extended `tests/test_tools/test_workflow_registry.py` — DEP-05 tests (lazy defaults, extended fields)
- [x] Extended `tests/test_tools/test_workflow_templates.py` — render_text + local scheduler tests

**Plan 09-02 Wave 0:**
- [x] Extended `tests/test_tools/test_workflow_templates.py` — PA/UiPath bundle shape tests (13 tests across 2 TestClass groups)
- [x] Extended `tests/test_tools/test_workflow_deploy.py` — guided/auto mode tests (8 tests across 2 TestClass groups)

**Plan 09-03 Wave 0:**
- [x] `tests/test_tools/test_workflow_manage.py` — 19 tests across 5 TestClass groups (list, pause, rollback, retire, health_check)

**Total Phase 9 tests:** 35 tests in `test_workflow_deploy.py` + `test_workflow_manage.py`, plus lazy-default registry extensions, plus PA/UiPath bundle sub-classes in `test_workflow_templates.py`, plus 3 registry_factory registration tests.

**Framework install:** None required — pytest + pytest-asyncio already installed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| flow_import.zip imports successfully in flow.microsoft.com | DEP-02 | Requires live PA tenant and browser interaction; Microsoft does not publish a programmatic import validator | 1. Generate a workflow with `workflow_deploy(deploy_mode="guided", target="power_automate", schedule="0 8 * * *")`. 2. Open flow.microsoft.com → My flows → Import Package (Legacy). 3. Select generated `flow_import.zip`. 4. Verify import succeeds with displayName `Yigthinker: <workflow_name>` and Recurrence trigger. 5. Trigger the flow manually to confirm. |
| UiPath .nupkg stub opens in Studio 23.10+ | DEP-02 | Requires UiPath Studio install; stub XAML is intentionally minimal (user adds Python Scope) | 1. Generate with `target="uipath"`. 2. Rename `uipath_guided/process_package.zip` to `.nupkg`. 3. Open in UiPath Studio. 4. Verify project loads and `Main.xaml` shows empty Sequence with placeholder comment. 5. Drop in a Python Scope + Run Python Script activity. 6. Publish to Orchestrator. |
| Generated task_scheduler.xml imports via schtasks | DEP-01 | Requires Windows host with admin shell | 1. Run `schtasks /create /xml "local_guided\task_scheduler.xml" /tn "YT_Test"`. 2. Verify task appears in Task Scheduler GUI with correct trigger. 3. Run task manually to verify it executes main.py. |
| Auto-mode MCP hand-off to Phase 12 MCP package | DEP-03, DEP-04 | Requires Phase 12 MCP server package, which does not yet exist | 1. (When Phase 12 ships) Install yigthinker_pa_mcp. 2. Run `workflow_deploy(deploy_mode="auto", target="power_automate", ...)`. 3. Verify returned `next_steps.suggested_tool = "power_automate_create_flow"` and `next_steps.bundle_path` points at the staged guided bundle. 4. Verify LLM uses next_steps to call the MCP tool and registry status flips from `pending_auto_deploy` to `active`. |
| Rollback instructional next-step is LLM-usable | LCM-04 | End-to-end flow involves LLM interpreting returned next_steps and issuing follow-up workflow_deploy call | 1. Generate v1 and v2 for a workflow. 2. Call `workflow_manage(action="rollback", workflow_name=X, target_version=1)`. 3. Inspect returned `next_steps` payload. 4. Verify LLM can parse and issue a follow-up `workflow_deploy` action using the structured next-step. |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-11 (audit trail below)

---

## Validation Audit 2026-04-11

| Metric | Count |
|--------|-------|
| Requirements audited | 11 |
| COVERED (green) | 11 |
| PARTIAL (needs work) | 0 |
| MISSING (no test) | 0 |
| Gaps filled by auditor | 0 (none needed) |
| Escalated to manual-only | 0 |

**Audit notes:**

1. Phase 9 delivered all 14 planned task-test pairs. Tests are organized into TestClass groups inside `test_workflow_deploy.py` and `test_workflow_manage.py` rather than flat functions — this is a more consistent style than the original draft plan anticipated but is fully automated and passing.

2. Added `09-03-06` row to Per-Task Verification Map to cover the registry-factory gate tests for `workflow_manage` (`TestWorkflowManageRegistration`). These tests were not in the original draft but exist in `tests/test_tools/test_registry_factory.py` and validate that the behavior/workflow gates guard tool registration correctly — they belong to Plan 09-03's behavior of "WorkflowManageTool is registered under the workflow gate".

3. Phase 9 VERIFICATION.md (2026-04-10) reported "78 passed in 1.00s" across the 5 Phase-9-touched test files and "603 passed in 12.79s" full-suite. Re-running the Phase 9 files today: 35 passed in `test_workflow_deploy.py + test_workflow_manage.py` (matches). All tests still green.

4. `test_deploy_writes_manifest_metadata` is added to 09-01-04 row — the original draft only listed `test_local_mode` but the full `test_workflow_deploy.py::test_local_mode` scope was split into granular tests during execution. DEP-05 metadata write-through is covered by both `test_deploy_writes_registry_metadata` and `test_deploy_writes_manifest_metadata`.

5. Added an auto-mode MCP hand-off manual test entry since Phase 12 package does not yet exist — the hand-off path is unit-tested via monkeypatching but the end-to-end LLM→MCP call cannot be verified until Phase 12 ships.

6. No auditor subagent spawn required — all 11 requirements have existing, passing coverage.

**Status:** `nyquist_compliant: true`, `wave_0_complete: true`.
