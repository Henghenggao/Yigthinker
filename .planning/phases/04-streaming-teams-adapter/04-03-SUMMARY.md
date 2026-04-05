---
phase: 04-streaming-teams-adapter
plan: 03
subsystem: gateway, tui
tags: [websocket, streaming, textual, markdown-stream, cursor-blink]

requires:
  - phase: 04-01
    provides: "Provider stream() async generators and AgentLoop on_token callback"
provides:
  - "Gateway broadcasts TokenStreamMsg to WS clients during LLM streaming"
  - "TUI renders tokens incrementally via Textual MarkdownStream"
  - "Blinking block cursor during active streaming (D-12)"
  - "Mid-stream tool_call handling: stop stream, remove cursor, mount ToolCard (D-11)"
affects: [05-memory-dream, tui, gateway]

tech-stack:
  added: []
  patterns:
    - "MarkdownStream for incremental token rendering in Textual TUI"
    - "Blink timer pattern: set_interval + display toggle for cursor visibility"
    - "Async helper methods for stream cleanup to avoid Textual layout conflicts"

key-files:
  created: []
  modified:
    - yigthinker/gateway/server.py
    - yigthinker/tui/app.py
    - yigthinker/tui/styles.tcss
    - yigthinker/tui/widgets/tool_card.py
    - tests/test_gateway/test_server.py
    - tests/test_tui/test_app.py

key-decisions:
  - "Use asyncio.ensure_future for fire-and-forget stream writes to avoid blocking synchronous _on_ws_message callback"
  - "Use Textual set_interval timer + display toggle for cursor blink instead of CSS keyframes (Textual CSS does not support @keyframes)"
  - "Refactor mid-stream tool_call to async _handle_tool_call_midstream helper to prevent Textual layout conflicts when mounting ToolCard during stream cleanup"

patterns-established:
  - "Streaming widget lifecycle: mount temp Markdown widget -> get_stream -> write tokens -> stop -> remove widget -> write final text to ChatLog"
  - "Cursor lifecycle: mount Static cursor -> start blink timer -> stop timer + remove cursor on finalize/tool_call"

requirements-completed: [STRM-03, STRM-04]

duration: 8min
completed: 2026-04-05
---

# Phase 04 Plan 03: Gateway + TUI Streaming Pipeline Summary

**Gateway broadcasts TokenStreamMsg per token chunk to WS clients, TUI renders incrementally via Textual MarkdownStream with blinking block cursor**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-05T20:09:04Z
- **Completed:** 2026-04-05T20:17:50Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Gateway on_token callback broadcasts TokenStreamMsg to all WS clients attached to the streaming session (STRM-03)
- TUI mounts temporary Markdown widget and uses MarkdownStream for token-by-token incremental rendering (STRM-04, amended D-10)
- Blinking block cursor appears during active streaming generation, removed on response_done (D-12)
- Mid-stream tool_call handling: stops stream, removes cursor, then mounts ToolCard (D-11)
- 4 new integration tests verifying streaming broadcast, token rendering, cursor lifecycle, and mid-stream tool_call handling
- Full test suite passes (319 tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Gateway on_token broadcast, TUI streaming render, and blinking cursor** - `dbb3c08` (feat)
2. **Task 2: Streaming integration tests for Gateway and TUI (including cursor lifecycle)** - `86781f7` (feat)

## Files Created/Modified
- `yigthinker/gateway/server.py` - Added TokenStreamMsg import, _on_token callback closure, passes on_token to AgentLoop.run()
- `yigthinker/tui/app.py` - Added token message handler, _finalize_stream, _blink_cursor, _handle_tool_call_midstream, _mount_tool_card methods; streaming state variables
- `yigthinker/tui/styles.tcss` - Added #streaming-md and #stream-cursor CSS rules
- `yigthinker/tui/widgets/tool_card.py` - Renamed _render to _refresh_content to avoid shadowing Textual's internal _render method; set initial content in __init__
- `tests/test_gateway/test_server.py` - Added test_streaming_broadcast_sends_token_msgs; updated FakeAgentLoop/RestoringAgent/SlowAgentLoop to accept **kwargs
- `tests/test_tui/test_app.py` - Added test_token_streaming_creates_markdown_widget, test_token_streaming_handles_tool_call_midstream, test_blinking_cursor_lifecycle

## Decisions Made
- Used asyncio.ensure_future for fire-and-forget stream writes (consistent with existing tool event pattern)
- Textual set_interval timer + display toggle for cursor blink (Textual CSS has no @keyframes support)
- Refactored mid-stream tool_call to async helper to avoid Textual layout conflicts during widget mount

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] FakeAgentLoop signatures missing **kwargs**
- **Found during:** Task 1 (Gateway streaming broadcast)
- **Issue:** FakeAgentLoop, RestoringAgent, and SlowAgentLoop in test_server.py didn't accept the new on_token kwarg, causing TypeError during handle_message
- **Fix:** Added **kwargs to all three test agent loop classes
- **Files modified:** tests/test_gateway/test_server.py
- **Verification:** All existing gateway tests pass
- **Committed in:** dbb3c08 (Task 1 commit)

**2. [Rule 1 - Bug] ToolCard._render() shadowed Textual internal _render method**
- **Found during:** Task 2 (Streaming integration tests)
- **Issue:** ToolCard defined _render() which shadowed Textual's internal Widget._render(), causing AttributeError ('NoneType' has no attribute 'get_height') during layout computation when mounting ToolCard dynamically
- **Fix:** Renamed _render() to _refresh_content(); set initial content in __init__ via super().__init__(initial_content); removed on_mount _render call
- **Files modified:** yigthinker/tui/widgets/tool_card.py
- **Verification:** All 319 tests pass, including new mid-stream tool_call test
- **Committed in:** 86781f7 (Task 2 commit)

**3. [Rule 1 - Bug] Synchronous ToolCard mount during stream cleanup caused layout conflict**
- **Found during:** Task 2 (Streaming integration tests)
- **Issue:** Mid-stream tool_call handler used ensure_future for stream.stop() and cursor.remove() but mounted ToolCard synchronously in the same frame, causing Textual layout computation errors
- **Fix:** Refactored to async _handle_tool_call_midstream helper that awaits stream cleanup before mounting ToolCard; extracted _mount_tool_card helper for DRY
- **Files modified:** yigthinker/tui/app.py
- **Verification:** test_token_streaming_handles_tool_call_midstream passes
- **Committed in:** 86781f7 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. The ToolCard bug was pre-existing but only manifested during dynamic mounting in streaming tests.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all streaming functionality is fully wired end-to-end.

## Next Phase Readiness
- End-to-end streaming pipeline complete: Provider -> AgentLoop -> Gateway -> WebSocket -> TUI
- Phase 04 all 3 plans complete (streaming infrastructure, Teams adapter, streaming pipeline)
- Ready for Phase 05 (Memory & Dream) or any downstream work

## Self-Check: PASSED

All files exist, all commit hashes verified, SUMMARY.md created.

---
*Phase: 04-streaming-teams-adapter*
*Completed: 2026-04-05*
