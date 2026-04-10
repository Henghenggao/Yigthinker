---
phase: 9
slug: deployment-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` (asyncio_mode = "auto") |
| **Quick run command** | `python -m pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_manage.py tests/test_tools/test_workflow_templates.py -x -q` |
| **Full suite command** | `python -m pytest -x -q` |
| **Estimated runtime** | Quick: ~3s, Full: ~15s (~550 tests + new Phase 9 tests) |

---

## Sampling Rate

- **After every task commit:** Run the task-specific test file (e.g., `pytest tests/test_tools/test_workflow_deploy.py -x -q`)
- **After every plan wave:** Run the full quick command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | DEP-05 | unit | `pytest tests/test_tools/test_workflow_registry.py::test_lazy_defaults_on_read -x -q` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | DEP-01 | unit | `pytest tests/test_tools/test_workflow_templates.py::test_render_text_skips_ast -x -q` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | DEP-01 | unit | `pytest tests/test_tools/test_workflow_templates.py::test_local_scheduler_templates -x -q` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | DEP-01, DEP-05 | unit+integration | `pytest tests/test_tools/test_workflow_deploy.py::test_local_mode -x -q` | ❌ W0 | ⬜ pending |
| 09-01-05 | 01 | 1 | DEP-01 | unit | `pytest tests/test_tools/test_workflow_registry_factory.py::test_workflow_deploy_registered -x -q` | ✅ (extend) | ⬜ pending |
| 09-02-01 | 02 | 2 | DEP-02 | unit | `pytest tests/test_tools/test_workflow_templates.py::test_guided_pa_bundle -x -q` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 2 | DEP-02 | unit | `pytest tests/test_tools/test_workflow_templates.py::test_guided_uipath_bundle -x -q` | ❌ W0 | ⬜ pending |
| 09-02-03 | 02 | 2 | DEP-02, DEP-05 | integration | `pytest tests/test_tools/test_workflow_deploy.py::test_guided_mode -x -q` | ❌ W0 | ⬜ pending |
| 09-02-04 | 02 | 2 | DEP-03, DEP-04, DEP-05 | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_auto_mode -x -q` | ❌ W0 | ⬜ pending |
| 09-03-01 | 03 | 2 | LCM-01, LCM-02 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_list_and_inspect -x -q` | ❌ W0 | ⬜ pending |
| 09-03-02 | 03 | 2 | LCM-03 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_pause_resume -x -q` | ❌ W0 | ⬜ pending |
| 09-03-03 | 03 | 2 | LCM-04 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_rollback -x -q` | ❌ W0 | ⬜ pending |
| 09-03-04 | 03 | 2 | LCM-05 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_retire -x -q` | ❌ W0 | ⬜ pending |
| 09-03-05 | 03 | 2 | LCM-06 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_health_check_with_empty_data -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Each plan's Wave 0 (first task) creates test stubs BEFORE implementation code. Proven pattern from Phase 8.

**Plan 09-01 Wave 0:**
- [ ] `tests/test_tools/test_workflow_deploy.py` — stubs for DEP-01 (test_local_mode, test_invalid_target_mode_combo)
- [ ] Extend `tests/test_tools/test_workflow_registry.py` — stubs for DEP-05 (test_lazy_defaults_on_read, test_extended_fields_write_through)
- [ ] Extend `tests/test_tools/test_workflow_templates.py` — stubs for new render_text() (test_render_text_skips_ast, test_render_text_runs_credential_scanner, test_local_scheduler_templates)

**Plan 09-02 Wave 0:**
- [ ] Extend `tests/test_tools/test_workflow_templates.py` — stubs for DEP-02 (test_guided_pa_bundle, test_guided_uipath_bundle, test_flow_import_zip_structure)
- [ ] Extend `tests/test_tools/test_workflow_deploy.py` — stubs for DEP-02/03/04 (test_guided_mode, test_auto_mode_returns_next_steps, test_auto_mode_mcp_missing_error)

**Plan 09-03 Wave 0:**
- [ ] `tests/test_tools/test_workflow_manage.py` — stubs for LCM-01 through LCM-06 (test_list_and_inspect, test_pause_resume, test_rollback, test_retire, test_health_check_with_empty_data, test_health_check_overdue)

**Framework install:** None — pytest + pytest-asyncio already installed per Phase 8.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| flow_import.zip imports successfully in flow.microsoft.com | DEP-02 | Requires live PA tenant and browser interaction; Microsoft does not publish a programmatic import validator | 1. Generate a workflow with `workflow_deploy(mode=guided, target=power_automate)`. 2. Open flow.microsoft.com → My flows → Import. 3. Select generated `flow_import.zip`. 4. Verify import succeeds (may require mapping Outlook connector). 5. Trigger the flow manually to confirm it works. |
| UiPath .nupkg stub opens in Studio | DEP-02 | Requires UiPath Studio 23.10+ installed; stub XAML is intentionally minimal and requires user to add Python Scope activity | 1. Generate workflow with `target=uipath`. 2. Open `uipath_guided/process_package.zip` (renamed .nupkg) in UiPath Studio. 3. Verify project loads without errors. 4. Setup guide instructs user to add Python Scope activity referencing main.py. |
| Generated task_scheduler.xml imports via schtasks | DEP-01 | Requires Windows host with admin shell | 1. Run `schtasks /create /xml "local_guided\task_scheduler.xml" /tn "YT_Test"`. 2. Verify task appears in Task Scheduler GUI with correct trigger. 3. Run task manually to verify it executes main.py. |
| Rollback instructional next-step is LLM-usable | LCM-04 | End-to-end flow involves LLM interpreting returned next_steps and issuing follow-up workflow_deploy call | 1. Generate v1 and v2. 2. Call `workflow_manage(action=rollback, workflow_name=X, target_version=1)`. 3. Inspect returned `next_steps` payload. 4. Verify LLM can parse and call the suggested workflow_deploy action. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
