---
phase: quick-260414-mu3
plan: 01
subsystem: agent-loop
tags: [asyncio, concurrency, truncation, fallback, microcompact, teams, adaptive-cards]

requires:
  - phase: core-agent-loop
    provides: AgentLoop, _execute_tool, YigthinkerTool protocol

provides:
  - Concurrent tool execution via asyncio.gather for safe tools
  - Tool result truncation at 8000 chars with descriptive suffix
  - Max-tokens auto-recovery up to 3 retries with continuation prompt
  - Fallback LLM provider wiring via builder.py
  - Microcompact pass before SmartCompact (replace old referenced tool_results)
  - Teams progressive feedback via render_tool_progress and on_tool_event passthrough

affects: [agent-loop, gateway, teams-adapter, tool-protocol]

tech-stack:
  added: []
  patterns:
    - "is_concurrency_safe protocol attribute for concurrent tool batching"
    - "_execute_tool_batch partitions safe/unsafe, asyncio.gather for safe, serial for unsafe"
    - "Microcompact as lightweight pre-pass before lossy SmartCompact"
    - "on_tool_event callback passthrough from gateway to channel adapters"

key-files:
  created:
    - tests/test_channels/test_teams_cards.py
  modified:
    - yigthinker/tools/base.py
    - yigthinker/agent.py
    - yigthinker/builder.py
    - yigthinker/gateway/server.py
    - yigthinker/channels/teams/cards.py
    - yigthinker/channels/teams/adapter.py
    - yigthinker/tools/dataframe/df_profile.py
    - yigthinker/tools/sql/schema_inspect.py
    - yigthinker/tools/exploration/explore_overview.py
    - yigthinker/tools/exploration/explore_drilldown.py
    - yigthinker/tools/exploration/explore_anomaly.py
    - yigthinker/tools/visualization/chart_recommend.py
    - yigthinker/tools/finance/finance_calculate.py
    - yigthinker/tools/finance/finance_analyze.py
    - yigthinker/tools/finance/finance_validate.py
    - yigthinker/tools/forecast/forecast_evaluate.py
    - tests/test_agent.py

key-decisions:
  - "is_concurrency_safe defaults to False via getattr -- tools without it remain serial"
  - "Microcompact lives on AgentLoop (not compact.py) -- only needs message structure access"
  - "Fallback provider is best-effort -- builder.py catches all exceptions on creation"
  - "Max-tokens recovery cap at 3 -- prevents infinite loops with non-terminating models"
  - "Teams progress cards are fire-and-forget -- exceptions silently swallowed"

patterns-established:
  - "is_concurrency_safe: class attribute on tools to opt into concurrent execution"
  - "_execute_tool_batch: partition-then-gather pattern for mixed safe/unsafe batches"
  - "on_tool_event passthrough: gateway propagates tool events to channel adapters"

requirements-completed: [QUICK-MU3]

duration: 6min
completed: 2026-04-14
---

# Quick 260414-mu3: Agent Loop Concurrent Upgrade Summary

**Concurrent tool execution via asyncio.gather, result truncation at 8K chars, max_tokens auto-recovery, fallback provider, microcompact before SmartCompact, and Teams progress cards**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-14T14:39:09Z
- **Completed:** 2026-04-14T14:45:32Z
- **Tasks:** 2
- **Files modified:** 18

## Accomplishments

- Added `is_concurrency_safe` to YigthinkerTool protocol and marked 10 read-only tools as safe for concurrent execution
- Implemented `_execute_tool_batch` that partitions tool calls into safe (asyncio.gather) and unsafe (serial) groups, maintaining original result ordering
- Added tool result truncation at 8000 chars with informative suffix mentioning total size and variable registry
- Added max_tokens auto-recovery: injects continuation prompt up to 3 times when LLM hits output limit
- Wired fallback_provider through builder.py -- on primary provider failure, automatically retries with fallback model
- Added `_microcompact` pre-pass: replaces old referenced tool_result contents before falling through to lossy SmartCompact
- Added Teams progressive feedback: `render_tool_progress` card + `_send_progress_card` fire-and-forget method + `on_tool_event` gateway passthrough
- Added 12 new tests covering all 6 upgrade areas (9 agent + 3 teams cards)

## Task Commits

Each task was committed atomically:

1. **Task 1: Protocol extension + concurrent batch + result truncation + error recovery + microcompact + fallback** - `c3f0822` (feat)
2. **Task 2: Teams progressive feedback + gateway on_tool_event passthrough + comprehensive tests** - `309d80b` (feat)

## Files Created/Modified

- `yigthinker/tools/base.py` - Added is_concurrency_safe: bool = False to YigthinkerTool protocol
- `yigthinker/agent.py` - Added MAX_RESULT_CHARS, _execute_tool_batch, _microcompact, fallback_provider, max_tokens recovery, result truncation
- `yigthinker/builder.py` - Fallback provider construction from settings.fallback_model, passed to AgentLoop
- `yigthinker/gateway/server.py` - Added on_tool_event param to handle_message, passthrough in _on_tool_event closure
- `yigthinker/channels/teams/cards.py` - Added render_tool_progress method to TeamsCardRenderer
- `yigthinker/channels/teams/adapter.py` - Added _send_progress_card and on_tool_event callback in _process_and_respond
- `yigthinker/tools/dataframe/df_profile.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/sql/schema_inspect.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/exploration/explore_overview.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/exploration/explore_drilldown.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/exploration/explore_anomaly.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/visualization/chart_recommend.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/finance/finance_calculate.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/finance/finance_analyze.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/finance/finance_validate.py` - Marked is_concurrency_safe = True
- `yigthinker/tools/forecast/forecast_evaluate.py` - Marked is_concurrency_safe = True
- `tests/test_agent.py` - Added 9 new tests for concurrent execution, truncation, recovery, fallback, microcompact
- `tests/test_channels/test_teams_cards.py` - Created with 3 tests for card rendering including progress cards

## Decisions Made

- `is_concurrency_safe` defaults to False via `getattr(tool, "is_concurrency_safe", False)` -- existing tools without the attribute remain serial without code changes
- Microcompact lives on AgentLoop as `_microcompact` method, not in compact.py -- it only needs message structure access, not SmartCompact config
- Fallback provider is best-effort -- builder.py catches all exceptions on creation so a bad fallback_model config never breaks startup
- Max-tokens recovery capped at 3 retries -- prevents infinite loops with models that consistently hit output limits
- Teams progress cards are fire-and-forget -- all exceptions silently swallowed to never break message processing
- on_tool_event passthrough appended after WS broadcast in gateway closure -- channel adapters receive same events as WS clients

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully wired.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. To enable fallback provider, users add `fallback_model` to their settings.json.

## Next Phase Readiness

- Agent loop now supports concurrent tool execution, result truncation, error recovery, and fallback providers
- Teams adapter delivers progressive feedback during long agent runs
- 10 read-only tools marked as concurrency-safe; additional tools can be marked by adding `is_concurrency_safe = True`

---
*Plan: quick-260414-mu3*
*Completed: 2026-04-14*

## Self-Check: PASSED

All 18 key files verified present. Both task commits (c3f0822, 309d80b) found in git log. 24/24 tests pass.
