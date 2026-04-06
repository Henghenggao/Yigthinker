# Phase 5: Session Memory & Auto Dream - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable cross-session knowledge accumulation. The agent remembers key findings within a session (surviving context compaction) and builds domain knowledge across sessions via background consolidation ("dreaming"). No new tools, no new UI — this is internal plumbing that makes existing tools smarter over time.

</domain>

<decisions>
## Implementation Decisions

### Memory Extraction Strategy
- **D-01:** LLM extraction every N turns (default 5, configurable via `extract_frequency`). After every Nth tool call, send recent tool results to the session's LLM with a structured extraction prompt targeting the MEMORY_TEMPLATE categories.
- **D-02:** Use the same LLM provider as the session — no dedicated extraction model. Extraction prompt is short, cost is minimal.
- **D-03:** Extract into the existing MEMORY_TEMPLATE categories: Data Source Knowledge, Business Rules & Patterns, Errors & Corrections, Key Findings, Analysis Log.
- **D-04:** Extraction runs in the background via `asyncio.create_task` — non-blocking, user can continue chatting.

### Dream Consolidation Approach
- **D-05:** Auto Dream reads per-session MEMORY.md files from recent sessions, sends them to the LLM with a "merge and deduplicate" prompt, and writes consolidated global MEMORY.md. Uses the same template structure.
- **D-06:** Use the same provider as the last session's configured provider — no separate dream provider config.
- **D-07:** Soft cap with LLM-driven pruning. When global MEMORY.md exceeds ~4K tokens, the dream LLM prunes least-relevant entries during merge. Keeps memory focused and injectable.

### Hook Wiring & Lifecycle
- **D-08:** AgentLoop.run() fires SessionStart at entry and SessionEnd at exit. This covers both CLI REPL and Gateway paths — every run() call is a session turn boundary.
- **D-09:** AgentLoop checks token budget before each LLM call. If messages exceed budget, fire PreCompact hook (which injects session memory into the compacted context), then run SmartCompact.
- **D-10:** Auto Dream is registered as a SessionEnd hook. When AgentLoop.run() completes, the hook fires, checks thresholds (24h + 3 sessions), and runs dream in background if criteria met. Follows the hook-over-hardcoded-logic architecture principle.

### Memory Loading & Context Injection
- **D-11:** Persisted memories are injected as a dedicated section in the system prompt. ContextManager already manages the 20% system prompt token budget — memories share this allocation.
- **D-12:** No dedicated memory budget — memories share the existing 20% system prompt allocation. If memories are large, ContextManager compresses other system content.
- **D-13:** Memory files are plain Markdown at known paths (`~/.yigthinker/memory/MEMORY.md` for global, project-level for per-project). Users can read, edit, or delete directly. Transparent and debuggable.

### Claude's Discretion
None — all areas discussed and decided.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Design
- `docs/superpowers/specs/2026-04-01-yigthinker-design.md` — Full architecture spec including Session Memory and Auto Dream design
- `CLAUDE.md` — Architecture principles, hook pattern, context manager token budgets

### Existing Memory Implementation (stubs to complete)
- `yigthinker/memory/session_memory.py` — MemoryManager class with record_turn(), extraction frequency, MEMORY_TEMPLATE, file paths
- `yigthinker/memory/auto_dream.py` — AutoDream class with threshold checks, DreamState persistence, FileLock pattern, stub _do_dream()
- `yigthinker/memory/compact.py` — SmartCompact class with token-aware compaction and memory injection into message list

### Integration Points
- `yigthinker/agent.py` — AgentLoop.run() where SessionStart/SessionEnd/PreCompact hooks must fire
- `yigthinker/hooks/executor.py` — HookExecutor.run() for firing hook events
- `yigthinker/hooks/registry.py` — HookRegistry for registering memory hooks
- `yigthinker/types.py` — HookEvent type with SessionStart/SessionEnd/PreCompact event types already defined
- `yigthinker/session.py` — SessionContext that holds message history and VarRegistry
- `yigthinker/settings.py` — DEFAULT_SETTINGS with `auto_dream: True` already present

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MemoryManager` class: turn counter, frequency check, file path derivation, template creation, memory loading — needs extraction logic added
- `AutoDream` class: threshold checks (hours + session count), DreamState persistence, FileLock for concurrent safety — needs LLM consolidation logic
- `SmartCompact` class: token-aware compaction with memory injection — needs to be wired into AgentLoop
- `HookExecutor` + `HookRegistry`: fully functional hook infrastructure — just needs SessionStart/SessionEnd/PreCompact events fired from AgentLoop
- `MEMORY_TEMPLATE` in session_memory.py: 5-category template for structured memory

### Established Patterns
- Hook pattern: `HookEvent(event_type, tool_name, data)` → `HookResult.ALLOW/WARN/BLOCK`
- Background tasks: `asyncio.create_task` for fire-and-forget (used in Gateway streaming, Phase 4)
- Provider access: `AgentLoop` holds `self._provider` (LLMProvider) — can be passed to extraction/dream
- Settings: `load_settings()["auto_dream"]` flag already exists for enabling/disabling

### Integration Points
- `AgentLoop.run()` — main loop, needs SessionStart/SessionEnd hook firing and PreCompact check
- `AgentLoop._execute_tool()` — PostToolUse is already fired here, record_turn() should follow
- `ContextManager.build_system_prompt()` — needs to include loaded memory content
- `__main__._build()` — where MemoryManager and AutoDream hooks should be registered

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches based on existing stub implementations.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-session-memory-auto-dream*
*Context gathered: 2026-04-05*
