---
phase: 12-power-automate-mcp-server
plan: 07
subsystem: workflow
tags: [mcp, power-automate, drift-guard, naming-convention]

# Dependency graph
requires:
  - phase: 12-05
    provides: "TOOL_REGISTRY with 5 PA tool handlers"
  - phase: 11-07
    provides: "UiPath drift-guard test pattern in test_mcp_detection.py"
provides:
  - "7 naming drift fixes aligning core workflow tools with shipped PA MCP package"
  - "rpa-pa optional extra in core pyproject.toml"
  - "PA drift-guard assertions preventing regression of canonical identifiers"
affects: [12-08, workflow-deploy-auto-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Drift-guard regression tests using regex scan of source files (Phase 11 UiPath + Phase 12 PA)"

key-files:
  created: []
  modified:
    - yigthinker/tools/workflow/mcp_detection.py
    - yigthinker/tools/workflow/workflow_manage.py
    - tests/test_tools/test_workflow_deploy.py
    - tests/test_tools/test_mcp_detection.py
    - pyproject.toml

key-decisions:
  - "Extended existing test_mcp_detection.py rather than creating new file (D-29)"
  - "suggest_automation.py verified untouched per D-07"

patterns-established:
  - "PA drift guard pattern: regex scan for legacy identifiers + canonical assertion + find_spec shape pinning"

requirements-completed: [MCP-PA-03]

# Metrics
duration: 3min
completed: 2026-04-12
---

# Phase 12 Plan 07: Core Drift Cleanup + PA Drift Guard Summary

**Fixed 7 PA naming drift sites in core workflow tools and extended drift-guard test with PA regression assertions**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-12T09:46:20Z
- **Completed:** 2026-04-12T09:49:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- All 7 Phase 9/10 naming drift sites fixed per D-05 table (yigthinker_pa_mcp -> yigthinker_mcp_powerautomate, power_automate_create_flow -> pa_deploy_flow, pa-mcp -> rpa-pa)
- Added rpa-pa optional dependency extra to core pyproject.toml (parallels Phase 11 rpa-uipath)
- Extended Phase 11 drift-guard test with 3 PA-specific test functions and 3 PA legacy patterns
- Verified suggest_automation.py untouched (D-07 invariant preserved)

## Task Commits

Each task was committed atomically:

1. **Task 1: Apply 7 drift edits and add rpa-pa extra** - `0e863f7` (fix)
2. **Task 2: Extend drift-guard test with PA assertions** - `2aabbcd` (test)

## Files Created/Modified
- `yigthinker/tools/workflow/mcp_detection.py` - Fixed 3 drift sites: package name, suggested tool, install hint
- `yigthinker/tools/workflow/workflow_manage.py` - Fixed 1 drift site: PA MCP package name in pause/resume instruction
- `tests/test_tools/test_workflow_deploy.py` - Fixed 3 drift sites: auto-mode assertion literals
- `tests/test_tools/test_mcp_detection.py` - Extended with 3 PA legacy patterns + 3 PA test functions
- `pyproject.toml` - Added rpa-pa = ["yigthinker-mcp-powerautomate"] optional extra

## Decisions Made
- Extended existing test_mcp_detection.py with PA assertions rather than creating a separate file (per D-29)
- Added PA_LEGACY_PATTERNS as a separate dict for readability while also adding entries to the shared LEGACY_PATTERNS dict

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Core workflow tools now use canonical PA identifiers matching the shipped yigthinker-mcp-powerautomate package
- workflow_deploy auto mode will correctly detect and suggest the PA MCP package
- Drift-guard tests prevent regression of both UiPath (Phase 11) and PA (Phase 12) identifiers
- Ready for Phase 12 Plan 08 (README)

---
*Phase: 12-power-automate-mcp-server*
*Completed: 2026-04-12*
