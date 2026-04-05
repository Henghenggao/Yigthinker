---
phase: 04-streaming-teams-adapter
plan: 01
subsystem: providers
tags: [streaming, async-generator, llm-provider, agent-loop, callback]

# Dependency graph
requires:
  - phase: 01-agent-loop-infra
    provides: "AgentLoop.run() with on_tool_event callback, LLMProvider Protocol, all 4 providers"
provides:
  - "StreamEvent dataclass for typed streaming events"
  - "stream() async generator on all 4 LLM providers (Claude, OpenAI, Azure, Ollama)"
  - "AgentLoop.run() on_token callback parameter for per-chunk streaming"
affects: [04-streaming-teams-adapter, tui, gateway]

# Tech tracking
tech-stack:
  added: []
  patterns: ["AsyncIterator[StreamEvent] as provider stream() return type", "on_token callback parallel to on_tool_event in AgentLoop"]

key-files:
  created:
    - tests/test_providers/test_streaming.py
  modified:
    - yigthinker/types.py
    - yigthinker/providers/base.py
    - yigthinker/providers/claude.py
    - yigthinker/providers/openai.py
    - yigthinker/providers/ollama.py
    - yigthinker/agent.py
    - tests/test_agent.py

key-decisions:
  - "StreamEvent as dataclass with Literal type field (text/tool_use/done/error) for typed streaming events"
  - "Provider stream() yields StreamEvent; AgentLoop accumulates into synthetic LLMResponse for seamless tool-call processing"
  - "AzureProvider inherits stream() from OpenAIProvider with no changes needed"

patterns-established:
  - "Provider streaming: async def stream() -> AsyncIterator[StreamEvent] pattern for all providers"
  - "Agent streaming: on_token callback fires per text chunk, tool_use events accumulated then processed identically to non-streaming path"

requirements-completed: [STRM-01, STRM-02]

# Metrics
duration: 4min
completed: 2026-04-05
---

# Phase 04 Plan 01: Streaming Providers & AgentLoop Summary

**StreamEvent type, stream() async generators on all 4 LLM providers, and on_token callback in AgentLoop.run() for per-chunk token streaming**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-05T19:16:12Z
- **Completed:** 2026-04-05T19:20:34Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- StreamEvent dataclass with typed event categories (text, tool_use, done, error) in types.py
- stream() async generator implemented on ClaudeProvider (SDK stream context manager), OpenAIProvider (incremental tool_call accumulation), and OllamaProvider (NDJSON line parsing); AzureProvider inherits from OpenAI
- AgentLoop.run() uses provider.stream() when on_token callback is provided, fires callback per text chunk, and accumulates tool_uses for identical processing to the non-streaming path
- 10 new tests: 7 provider streaming tests + 3 agent streaming tests, all passing alongside existing tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Add StreamEvent type and provider stream() methods** - `3424cef` (feat)
2. **Task 2: Integrate streaming into AgentLoop.run() with on_token callback** - `838abd1` (feat)

## Files Created/Modified
- `yigthinker/types.py` - Added StreamEvent dataclass with type/text/tool_use/stop_reason/error fields
- `yigthinker/providers/base.py` - Added stream() method to LLMProvider Protocol
- `yigthinker/providers/claude.py` - stream() using client.messages.stream() context manager with text and content_block_stop handling
- `yigthinker/providers/openai.py` - stream() using create(stream=True) with incremental tool_call argument accumulation
- `yigthinker/providers/ollama.py` - stream() using httpx streaming with NDJSON aiter_lines() parsing
- `yigthinker/agent.py` - Added on_token parameter to run(), streaming path with StreamEvent accumulation
- `tests/test_providers/test_streaming.py` - 7 tests for all 4 provider stream() methods
- `tests/test_agent.py` - 3 tests for AgentLoop streaming integration

## Decisions Made
- StreamEvent uses a dataclass with Literal type field rather than separate event classes -- simpler, matches existing ToolResult pattern
- Provider stream() wraps entire body in try/except, yielding StreamEvent(type="error") on failure -- graceful degradation
- AgentLoop builds a synthetic LLMResponse from accumulated stream events, so existing tool execution, hook firing, and message history work identically without any changes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Claude stream test mock approach**
- **Found during:** Task 1 (test_streaming.py creation)
- **Issue:** AsyncMock for Anthropic SDK stream() context manager didn't work as expected -- the messages.stream() call returns a sync context manager, not a coroutine
- **Fix:** Created _FakeAnthropicStreamCtx helper class implementing proper async context manager and async iterator protocols
- **Files modified:** tests/test_providers/test_streaming.py
- **Verification:** All 7 streaming tests pass
- **Committed in:** 3424cef (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test mock approach adjusted for Anthropic SDK specifics. No scope creep.

## Issues Encountered
None beyond the mock approach adjustment documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- StreamEvent and provider stream() methods ready for Gateway WebSocket wiring (Plan 03)
- on_token callback ready for TUI integration
- Non-streaming path fully preserved for channel adapters (Teams, Feishu)

## Self-Check: PASSED

- All 9 key files verified present
- Commits 3424cef and 838abd1 verified in git log
- All 18 streaming + agent tests pass
- All 20 provider tests pass (no regression)

---
*Phase: 04-streaming-teams-adapter*
*Completed: 2026-04-05*
