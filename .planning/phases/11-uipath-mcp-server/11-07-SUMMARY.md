---
phase: 11-uipath-mcp-server
plan: 07
subsystem: core-drift-cleanup
tags: [drift-guard, mcp-detection, pyproject, rpa-uipath, d-07]
requires:
  - Plan 11-01..11-06 (yigthinker-mcp-uipath package must exist and be green)
provides:
  - Core workflow_deploy auto-mode correctly detects the real yigthinker_mcp_uipath package
  - pyproject.toml `rpa-uipath` optional extra for `pip install yigthinker[rpa-uipath]`
  - Regression-proof drift guard via tests/test_tools/test_mcp_detection.py
affects:
  - yigthinker/tools/workflow/mcp_detection.py
  - yigthinker/tools/workflow/workflow_manage.py
  - tests/test_tools/test_workflow_deploy.py
  - pyproject.toml
  - tests/test_tools/test_mcp_detection.py (new)
tech-stack:
  added: []
  patterns:
    - "Grep-based drift guard (Option C from Research Finding 11) -- no runtime imports"
    - "D-07 invariant enforced programmatically via pinned-identifier test"
key-files:
  created:
    - tests/test_tools/test_mcp_detection.py
  modified:
    - yigthinker/tools/workflow/mcp_detection.py
    - yigthinker/tools/workflow/workflow_manage.py
    - tests/test_tools/test_workflow_deploy.py
    - pyproject.toml
decisions:
  - "D-07 drift guard relaxed from `canonical_hits == 1` to `canonical_hits >= 1` because suggest_automation.py legitimately has two canonical references (one in module docstring, one in find_spec call). The `find_spec` call shape is still asserted exactly."
requirements: [MCP-UI-03]
metrics:
  duration: ~6min
  completed_date: "2026-04-11"
  tasks: 2
  files_touched: 5
---

# Phase 11 Plan 07: Core Drift Cleanup + Drift Guard Summary

Align core `yigthinker/tools/workflow/` MCP detection with the shipped
`yigthinker-mcp-uipath` package (Plans 11-01..11-06), add a `rpa-uipath`
optional-dependency extra to the core pyproject, and install a regression-proof
drift guard that pins the canonical identifiers and the D-07 `suggest_automation.py`
invariant.

## Objective

Fix the legacy identifier drift that existed in core since Phase 9 (when the
MCP package names were guessed as `yigthinker_uipath_mcp` /
`uipath_publish_package` / `yigthinker[uipath-mcp]`) so that
`workflow_deploy target=uipath deploy_mode=auto` actually detects the real
`yigthinker_mcp_uipath` package once users `pip install yigthinker[rpa-uipath]`.

## Tasks Executed

### Task 1 -- Fix drift in mcp_detection, workflow_manage, and test_workflow_deploy

Applied 6 literal string edits across 3 files per D-05:

1. `yigthinker/tools/workflow/mcp_detection.py:19` -- MCP_PACKAGE_MAP.uipath: `yigthinker_uipath_mcp` -> `yigthinker_mcp_uipath`
2. `yigthinker/tools/workflow/mcp_detection.py:29` -- suggested_tool: `uipath_publish_package` -> `ui_deploy_process`
3. `yigthinker/tools/workflow/mcp_detection.py:30` -- install_hint: `pip install yigthinker[uipath-mcp]` -> `pip install yigthinker[rpa-uipath]`
4. `yigthinker/tools/workflow/workflow_manage.py:238` -- `_toggle` instructional string uses canonical package name
5. `tests/test_tools/test_workflow_deploy.py:451` -- suggested_tool assertion: `ui_deploy_process`
6. `tests/test_tools/test_workflow_deploy.py:455` -- mcp_package assertion: `yigthinker_mcp_uipath`

**D-07 honored:** `yigthinker/tools/workflow/suggest_automation.py` NOT touched.
`git diff` against that file is empty across both task commits.

**Verification:** `pytest tests/test_tools/test_workflow_deploy.py -k "auto_mode" -x -q`
-> 4 passed, 12 deselected.

**Commit:** `484c211 fix(11-07): align MCP detection identifiers with shipped package name`

### Task 2 -- Add rpa-uipath pyproject extra and drift-guard test

Added to `pyproject.toml` `[project.optional-dependencies]`:

```toml
rpa-uipath = [
    "yigthinker-mcp-uipath",
]
```

Created `tests/test_tools/test_mcp_detection.py` with 3 tests:

1. **test_no_legacy_uipath_identifiers_in_workflow_tools** -- rglob-scans every
   `.py` under `yigthinker/tools/workflow/` for any of the 3 legacy regex patterns
   (`yigthinker_uipath_mcp`, `uipath_publish_package`, `yigthinker\[uipath-mcp\]`).
2. **test_canonical_uipath_identifiers_present_in_mcp_detection** -- asserts
   `mcp_detection.py` contains the three canonical strings after cleanup.
3. **test_suggest_automation_pinned_to_canonical_identifier** -- D-07 pin:
   asserts `suggest_automation.py` contains `>= 1` canonical match, zero legacy
   matches, and the exact `importlib.util.find_spec("yigthinker_mcp_uipath")`
   call shape.

Per D-15, the test is purely regex-based -- zero `import yigthinker_mcp_uipath`
lines, so core never imports the package at runtime or test time.

**Verification:**
- `python -c "import tomllib; assert 'rpa-uipath' in ..."` -> ok
- `pytest tests/test_tools/test_mcp_detection.py -x -q` -> 3 passed in 0.03s

**Commit:** `5575fbc feat(11-07): add rpa-uipath extra and MCP identifier drift guard`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] D-07 pin test relaxed from `== 1` to `>= 1`**

- **Found during:** Task 2 drafting
- **Issue:** The plan as written prescribed `canonical_hits == 1` for the
  `suggest_automation.py` D-07 pin, based on the (correct) observation that
  line 168 contains the single `find_spec("yigthinker_mcp_uipath")` call.
  However, the actual file ALSO has a second canonical reference at line 33,
  inside a module docstring that lists both MCP packages:
  `(yigthinker_mcp_powerautomate, yigthinker_mcp_uipath)`. Running the test
  as written would fail with `canonical_hits == 2`. Per D-07, I cannot edit
  `suggest_automation.py` to remove the docstring reference.
- **Fix:** Changed the assertion to `canonical_hits >= 1` and kept the zero-
  legacy-hits assertion and the exact `find_spec` call-shape assertion. The
  D-07 invariant remains fully enforced: the file must retain the canonical
  call shape and must not contain any legacy names.
- **Files modified:** `tests/test_tools/test_mcp_detection.py`
- **Commit:** `5575fbc`

### Architectural Changes

None -- this plan was entirely literal string edits + one new test file + one
pyproject.toml addition.

## Acceptance Criteria Verification

| Criterion | Result |
|-----------|--------|
| 6 legacy identifier hits replaced with canonical names | PASS (0 hits of any legacy pattern in `yigthinker/tools/workflow/`) |
| `yigthinker/tools/workflow/suggest_automation.py` unchanged (D-07) | PASS (`git diff` empty across both commits) |
| `pyproject.toml` has `rpa-uipath` optional extra | PASS |
| `tests/test_tools/test_mcp_detection.py` drift guard exists | PASS (3 tests) |
| `test_workflow_deploy.py::test_auto_mode_returns_next_steps` passes | PASS (4 auto_mode tests green) |
| Core workflow test suite still green | PASS (46/46 in workflow_deploy + mcp_detection + suggest_automation + workflow_manage) |
| Zero imports of `yigthinker_mcp_uipath` in core (D-15) | PASS (drift guard is regex-only, no runtime import) |
| Package regression still green | PASS (47/47 in packages/yigthinker-mcp-uipath) |
| Wave ordering honored: ran AFTER Plans 11-01..11-06 | PASS (last commit before this plan was 117c905 docs(11-06)) |

## Commits

| # | Hash | Subject |
|---|------|---------|
| 1 | `484c211` | `fix(11-07): align MCP detection identifiers with shipped package name` |
| 2 | `5575fbc` | `feat(11-07): add rpa-uipath extra and MCP identifier drift guard` |

## Files Touched

**Created (1):**
- `tests/test_tools/test_mcp_detection.py`

**Modified (4):**
- `yigthinker/tools/workflow/mcp_detection.py`
- `yigthinker/tools/workflow/workflow_manage.py`
- `tests/test_tools/test_workflow_deploy.py`
- `pyproject.toml`

## Handoff to Plan 11-08

Plan 11-08 (README + install docs) can now rely on:
- The canonical install incantation: `pip install yigthinker[rpa-uipath]`
- The canonical MCP tool name: `ui_deploy_process` (and the other 4 `ui_*` tools)
- The canonical module name: `yigthinker_mcp_uipath`
- Regression safety: the drift guard blocks future PRs from silently breaking
  any of these three names in `yigthinker/tools/workflow/`.

The two-step dev install (`pip install -e . && pip install -e packages/yigthinker-mcp-uipath[test]`)
should be documented in Plan 11-08's README per D-25.

## Self-Check: PASSED

- File `tests/test_tools/test_mcp_detection.py` exists
- Commit `484c211` exists in git log
- Commit `5575fbc` exists in git log
- `yigthinker/tools/workflow/mcp_detection.py` contains `yigthinker_mcp_uipath`, `ui_deploy_process`, `rpa-uipath`
- `yigthinker/tools/workflow/workflow_manage.py` contains `yigthinker_mcp_uipath`
- `tests/test_tools/test_workflow_deploy.py` contains `yigthinker_mcp_uipath` and `ui_deploy_process`
- `pyproject.toml` has `rpa-uipath` optional extra
- `git diff yigthinker/tools/workflow/suggest_automation.py` empty (D-07 invariant)
