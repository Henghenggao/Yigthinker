---
phase: 05-session-memory-auto-dream
plan: 01
subsystem: memory
tags: [llm-extraction, auto-dream, memory-consolidation, async]

requires:
  - phase: 01-agent-loop-infrastructure
    provides: LLMProvider protocol, Message/LLMResponse types, SessionContext

provides:
  - MemoryManager.extract_memories() sends recent turns to LLM and appends findings to MEMORY.md
  - AutoDream._consolidate_via_llm() merges session memories via LLM into global MEMORY.md
  - EXTRACTION_PROMPT with 5-category structured extraction
  - DREAM_PROMPT with ~4K token pruning instruction

affects: [05-02-PLAN, agent-loop-wiring, system-prompt-injection]

tech-stack:
  added: []
  patterns: [LLM-as-extraction-engine, append-not-overwrite memory, async dream consolidation]

key-files:
  created: []
  modified:
    - yigthinker/memory/session_memory.py
    - yigthinker/memory/auto_dream.py
    - tests/test_memory/test_session_memory.py
    - tests/test_memory/test_auto_dream.py

key-decisions:
  - "LLM extraction uses same provider as session (no dedicated extraction model)"
  - "Memory append uses section-aware insertion under matching H1 headers"
  - "AutoDream accepts memory_dirs list for testable memory scanning"
  - "Removed asyncio.to_thread; run_background is fully async"
  - "provider param defaults to None for backward compat with existing tests"

patterns-established:
  - "LLM-as-extractor: provider.chat() with structured prompt, no tools"
  - "Section-aware append: _parse_sections + _insert_after_header for MEMORY.md"

requirements-completed: [MEM-01, MEM-03]

duration: 3min
completed: 2026-04-06
---

# Phase 5 Plan 1: LLM Memory Extraction and Dream Consolidation Summary

**MemoryManager.extract_memories() sends recent conversation to LLM for structured knowledge extraction; AutoDream._consolidate_via_llm() merges per-session memories into global MEMORY.md with dedup and ~4K token pruning**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-06T12:43:55Z
- **Completed:** 2026-04-06T12:47:52Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- MemoryManager.extract_memories() sends last N*2 messages to session LLM, receives structured findings in 5 categories, and appends them to project MEMORY.md without overwriting existing content
- AutoDream.run_background() reads MEMORY.md from configured memory dirs, sends combined text to LLM for dedup/merge consolidation, writes result to global MEMORY.md, and updates DreamState
- Removed asyncio.to_thread from AutoDream (Research Pitfall 2) -- fully async now
- 12 new tests with mocked LLM providers covering extraction, consolidation, append semantics, pruning prompts, and state lifecycle

## Task Commits

Each task was committed atomically:

1. **Task 1: Add LLM extraction to MemoryManager** - `dae14da` (test: RED), `b4c2c8a` (feat: GREEN)
2. **Task 2: Add LLM consolidation to AutoDream** - `3887578` (test: RED), `78a23f8` (feat: GREEN)

_TDD tasks have two commits each (test -> feat)_

## Files Created/Modified

- `yigthinker/memory/session_memory.py` - Added EXTRACTION_PROMPT, extract_memories(), _append_to_memory(), _parse_sections(), _insert_after_header()
- `yigthinker/memory/auto_dream.py` - Added DREAM_PROMPT, _consolidate_via_llm(), _read_session_memories(), refactored run_background() to fully async with LLM provider
- `tests/test_memory/test_session_memory.py` - 6 new tests for extraction logic
- `tests/test_memory/test_auto_dream.py` - 6 new tests for dream consolidation logic

## Decisions Made

- LLM extraction uses the same provider as the session (no dedicated extraction model per D-02)
- Memory append uses section-aware insertion: _parse_sections splits by H1 headers, _insert_after_header places content under matching sections
- AutoDream accepts `memory_dirs` list parameter for testable memory directory scanning instead of hard-coded path scanning
- Removed `asyncio.to_thread` from run_background per Research Pitfall 2; method is now fully async
- `provider` parameter defaults to `None` in run_background() for backward compatibility with existing test that passes only 2 args

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Memory extraction and dream consolidation modules are complete and tested with mocked LLM
- Plan 05-02 can now wire these into the AgentLoop lifecycle: SessionStart/SessionEnd hooks, PreCompact memory injection, builder hook registration, system prompt injection
- MemoryManager needs to be instantiated in _build() and hooked into PostToolUse for record_turn()
- AutoDream needs SessionEnd hook registration to trigger dreaming after session completion

## Self-Check: PASSED

- All 4 source/test files exist on disk
- All 4 task commits verified in git log (dae14da, b4c2c8a, 3887578, 78a23f8)
- 33/33 memory tests passing

---
*Phase: 05-session-memory-auto-dream*
*Completed: 2026-04-06*
