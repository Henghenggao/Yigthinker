---
phase: 05-session-memory-auto-dream
plan: 02
subsystem: memory
tags: [agent-loop, lifecycle-hooks, memory-integration, compaction, system-prompt]

requires:
  - phase: 05-session-memory-auto-dream
    plan: 01
    provides: MemoryManager.extract_memories(), AutoDream.run_background(), SmartCompact

provides:
  - AgentLoop fires SessionStart/SessionEnd/PreCompact lifecycle hook events
  - Memory extraction runs as background task after tool calls via asyncio.create_task
  - SmartCompact compresses messages when token budget exceeded
  - MemoryManager and AutoDream registered in build_app() gated by feature flags
  - ContextManager.build_memory_section() formats loaded memories for system prompt
  - Loaded memories injected as system= parameter to LLM provider calls

affects: [system-prompt, agent-behavior, session-lifecycle]

tech-stack:
  added: []
  patterns: [lifecycle-hook-events, feature-gated-registration, background-extraction-task, system-prompt-injection]

key-files:
  created:
    - tests/test_agent_memory.py
  modified:
    - yigthinker/agent.py
    - yigthinker/builder.py
    - yigthinker/context_manager.py

key-decisions:
  - "Memory extraction runs as asyncio.create_task (fire-and-forget, never surfaces errors)"
  - "SessionEnd fires in finally block to guarantee execution even on timeout"
  - "HookRegistry created separately from HookExecutor in builder for explicit hook registration"
  - "Memory content injected via system= parameter on provider.chat()/stream() each iteration"
  - "build_memory_section truncates at 50% of system budget to leave room for other system content"

patterns-established:
  - "Lifecycle hook pattern: SessionStart at run() entry, SessionEnd in finally, PreCompact before LLM call"
  - "Feature-gated registration: gate() checks before creating memory subsystem components in builder"
  - "Background extraction: list(messages) snapshot + asyncio.create_task for non-blocking extraction"

requirements-completed: [MEM-01, MEM-02, MEM-03, MEM-04]

duration: 3min
completed: 2026-04-06
---

# Phase 5 Plan 2: AgentLoop Memory Wiring and Builder Registration Summary

**AgentLoop fires SessionStart/SessionEnd/PreCompact lifecycle events, triggers background memory extraction after tool calls, and builder.py registers MemoryManager/AutoDream gated by feature flags with system prompt injection**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-06T13:20:08Z
- **Completed:** 2026-04-06T13:23:34Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- AgentLoop.run() fires SessionStart before the loop, PreCompact when token budget exceeded, and SessionEnd in a finally block guaranteeing execution
- Background memory extraction via asyncio.create_task after tool calls with shallow-copy message snapshot to avoid mutation
- builder.py gates MemoryManager + SmartCompact on session_memory flag and AutoDream SessionEnd hook on auto_dream flag
- ContextManager.build_memory_section() formats loaded memories with truncation at 50% of system budget
- System prompt with accumulated knowledge passed to provider.chat() and provider.stream() on each iteration
- 6 new tests covering all lifecycle events, extraction triggering, compaction, and snapshot isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire AgentLoop with lifecycle events and memory integration** - `7b0baa3` (test: RED), `e22c385` (feat: GREEN)
2. **Task 2: Wire builder registration and system prompt injection** - `442fb16` (feat)

_TDD Task 1 has two commits (test -> feat)_

## Files Created/Modified

- `yigthinker/agent.py` - Added SessionStart/SessionEnd/PreCompact hook firing, memory extraction after tool calls, set_memory_manager/set_compact setters, _estimate_tokens/_format_vars_summary/_run_extraction helpers, system prompt passing to provider
- `yigthinker/builder.py` - Added feature-gated MemoryManager/SmartCompact creation, AutoDream SessionEnd hook registration, memory_manager on AppContext
- `yigthinker/context_manager.py` - Added build_memory_section() with truncation and system_budget property
- `tests/test_agent_memory.py` - 6 tests for lifecycle events, extraction, compaction, and snapshot isolation

## Decisions Made

- Memory extraction runs as asyncio.create_task with fire-and-forget semantics (errors silently suppressed per AutoDream pattern)
- SessionEnd fires in finally block to guarantee it runs even when the loop times out
- HookRegistry created separately from HookExecutor in builder to allow explicit hook registration before executor creation
- Memory content injected via system= parameter on each LLM call iteration (not once at start) so fresh extractions are picked up
- build_memory_section truncates at 50% of system budget (~20K tokens on 200K context) to leave room for other system content

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added build_memory_section to context_manager.py in Task 1**
- **Found during:** Task 1 (AgentLoop wiring)
- **Issue:** Agent.py compaction path calls ctx.context_manager.build_memory_section() but the method didn't exist yet (planned for Task 2)
- **Fix:** Added build_memory_section() and system_budget property to ContextManager in Task 1 to allow tests to pass
- **Files modified:** yigthinker/context_manager.py
- **Verification:** All 6 new tests pass
- **Committed in:** e22c385 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** build_memory_section() pulled forward from Task 2 into Task 1 for test completeness. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Full memory system is now wired: extraction happens automatically after tool calls, compaction preserves memory when budget exceeded, dream consolidates on session end, and loaded memories appear in system prompt
- Phase 05 (session-memory-auto-dream) is complete with both plans done
- All 337 tests pass across the full test suite (excluding optional-dependency forecast tests)

## Self-Check: PASSED

- All 4 created/modified files exist on disk
- All 3 task commits verified in git log (7b0baa3, e22c385, 442fb16)
- 50/50 memory + agent tests passing
- 337/337 full suite tests passing

---
*Phase: 05-session-memory-auto-dream*
*Completed: 2026-04-06*
