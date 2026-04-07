---
phase: quick
plan: 260407-o9s
subsystem: agent, gateway, memory, docs
tags: [asyncio, icacls, windows, compact, design-tokens, css]

requires: []
provides:
  - "GC-safe asyncio task storage pattern in AgentLoop._background_tasks"
  - "Platform-aware gateway token file protection (icacls on Windows, chmod on Unix)"
  - "Async SmartCompact.run() interface ready for future await-based compaction"
  - "docs/DESIGN.md design tokens reference for Phase 6 dashboard implementation"
affects: [06-web-dashboard, gateway]

tech-stack:
  added: []
  patterns:
    - "asyncio fire-and-forget pattern: store in set, discard via done-callback"
    - "Platform-branching for file permissions: sys.platform == 'win32'"

key-files:
  created:
    - docs/DESIGN.md
  modified:
    - yigthinker/agent.py
    - yigthinker/gateway/auth.py
    - yigthinker/memory/compact.py
    - tests/test_agent_memory.py
    - tests/test_gateway/test_auth.py
    - tests/test_memory/test_compact.py

key-decisions:
  - "Force-added docs/DESIGN.md to git despite docs/ being in .gitignore, because this file is a required reference for Phase 6 implementation"

patterns-established:
  - "asyncio fire-and-forget: self._background_tasks.add(task); task.add_done_callback(self._background_tasks.discard)"

requirements-completed: []

duration: 4min
completed: 2026-04-07
---

# Quick Plan 260407-o9s: Fix TODO Items Summary

**GC-safe asyncio task storage, Windows icacls token protection, async SmartCompact, and design token documentation for Phase 6**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-07T15:33:16Z
- **Completed:** 2026-04-07T15:37:28Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Fixed asyncio task reference leak: fire-and-forget `create_task` results now stored in `_background_tasks` set with done-callback cleanup, preventing GC collection of running tasks
- Added Windows-specific gateway token file protection using `icacls` with `/inheritance:r` and `/grant:r` for current user only; Unix continues to use `chmod 0o600`
- Converted `SmartCompact.run()` from sync to async def; updated `AgentLoop` call site to `await`
- Created `docs/DESIGN.md` with CSS custom properties (light + dark themes), component states table, screen layout, responsive breakpoints, accessibility requirements, and tool call display specs -- all sourced from CEO plan design review

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix asyncio task leak, Windows token protection, and async compact** - `1742ad5` (fix)
2. **Task 2: Update tests for task leak fix and async compact** - `a0559af` (test)
3. **Task 3: Create docs/DESIGN.md with design tokens and component specs** - `71fd6e6` (docs)

## Files Created/Modified
- `yigthinker/agent.py` - Added `_background_tasks` set, done-callback cleanup, `await` on compact.run()
- `yigthinker/gateway/auth.py` - Platform-aware file protection (icacls on Win32, chmod on Unix)
- `yigthinker/memory/compact.py` - Changed `def run()` to `async def run()`
- `tests/test_agent_memory.py` - Verify `add_done_callback` called on background tasks
- `tests/test_gateway/test_auth.py` - New `test_windows_uses_icacls` test
- `tests/test_memory/test_compact.py` - Converted 5 compact tests from sync to async
- `docs/DESIGN.md` - Design tokens and component specifications for web dashboard

## Decisions Made
- Force-added `docs/DESIGN.md` to git despite `docs/` being in `.gitignore`, because this file is a required reference artifact for Phase 6 dashboard implementation

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- Pre-existing flaky test `test_list_sessions_excludes_old_files` in `test_auto_dream.py` fails when run in full suite (test ordering dependency) but passes in isolation. Not caused by our changes. Logged as out-of-scope.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Design tokens documented and committed, ready for Phase 6 dashboard CSS implementation
- AgentLoop asyncio patterns are now GC-safe for production use
- Gateway token file protection works correctly on Windows

## Self-Check: PASSED

- All 7 files verified present on disk
- All 3 commit hashes verified in git log
- All 4 must_have artifact patterns confirmed (\_background\_tasks, icacls, async def run, --bg-primary)

---
*Plan: quick-260407-o9s*
*Completed: 2026-04-07*
