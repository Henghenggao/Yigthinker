# Project Research Summary

**Project:** Yigthinker — Multi-channel AI Agent Gateway, TUI, and Memory Systems
**Domain:** AI-powered data analysis agent with enterprise messaging integration
**Researched:** 2026-04-02
**Confidence:** HIGH

## Executive Summary

Yigthinker is a Python-based AI agent for financial and data analysis, and the current milestone is about making scaffolded code work end-to-end rather than building net-new features. The architecture — a Unified Agent Gateway pattern where a stateless AgentLoop serves all channels through a centralized FastAPI daemon — is fundamentally sound and already implemented. The stack choices (FastAPI, Textual, PyArrow, lark-oapi, msal, websockets) are validated and current. The key challenge is that a significant portion of scaffolded code is either silently broken (stubs returning success), blocked by a critical async/sync boundary bug in `_build()`, or has correctness issues that will manifest as data loss or security vulnerabilities in multi-session use.

The recommended approach is to fix the Agent Loop and foundational infrastructure first, then build outward. The dependency graph is strict: every downstream component (Gateway, TUI, channels, memory) calls `AgentLoop.run()`. The `_build()` function's `asyncio.run()` call breaks MCP tool loading inside the Gateway's event loop, and the shared `PermissionSystem` instance creates cross-session privilege escalation. These are blocking defects that must be resolved in Phase 1. The Gateway must then be stabilized before TUI or channel adapters can be meaningfully tested.

The top risks are not architectural but operational: ten documented pitfalls where code looks done but silently fails. The most critical are the `_build()` async nesting bug (MCP tools missing in gateway), the shared PermissionSystem contamination (privilege escalation across sessions), session hibernation's delete-before-confirm pattern (data loss on crash), the fire-and-forget task GC bug (Feishu messages silently dropped), and the df_transform sandbox escape via the `type` builtin (full sandbox bypass). All of these have clear, low-cost fixes documented in PITFALLS.md.

## Key Findings

### Recommended Stack

The existing stack is validated and requires no technology substitutions. The only actionable finding is that several `pyproject.toml` version floors are dangerously loose and would allow installing incompatible versions on fresh installs. The most critical: `pytest-asyncio` must be pinned to `>=1.0.0` (not `>=0.23.0`), `textual` to `>=8.0.0` (not `>=0.80.0`), and `pyarrow` to `>=20.0.0`. All installed versions in the development venv are correct; the issue is fresh install safety.

The one architectural decision still pending is whether to use Outgoing Webhooks (current) or a full Azure Bot Service registration for Teams. Outgoing Webhooks are sufficient for v1 but have a hard 10-second response timeout and cannot proactively message users. The Teams adapter as currently written cannot handle the Gateway's async processing within this constraint.

**Core technologies:**
- FastAPI + uvicorn: Gateway HTTP/WebSocket server — already implemented, no alternatives considered
- Textual 8.x: Terminal UI framework — only serious async TUI framework in Python 2025-2026
- websockets 16.x: TUI WebSocket client — purpose-built, used client-side only (server side is FastAPI)
- PyArrow 23.x + Parquet: DataFrame hibernation — columnar, typed, compressed; Snappy compression is the right tradeoff for ephemeral local files
- lark-oapi 1.5.x: Official Feishu/Lark SDK — the only supported option (community wrappers lag API changes)
- msal 1.35.x: Azure AD token acquisition for Teams — no alternatives for Azure AD auth
- filelock 3.25.x: Auto Dream concurrency — zero-dependency, cross-platform, already installed
- aiosqlite 0.22.x: Feishu event deduplication — async-safe SQLite for the dedup store
- pytest-asyncio 1.3.x: Async test support — pin floor to >=1.0.0 to avoid pre-breaking-change installs

**Do not add:** Redis, Celery, botbuilder-core, Chroma/Qdrant, polars, APScheduler, or msgpack/protobuf. All explicitly out of scope and add operational complexity without proportional value at this scale.

### Expected Features

The milestone focus is stabilization. NL-to-query is table stakes in 2026 (commoditized). Yigthinker's differentiation comes from cross-session memory, multi-channel enterprise messaging access, terminal-native TUI, and hook-based enterprise extensibility — none of which competitors (PandasAI, Julius AI, Tableau Pulse, Querio) offer.

**Must have (table stakes — fix or clarify now):**
- End-to-end agent loop — core path broken by `_build()` async nesting bug
- Agent loop safety guardrails — iteration limit (25), wall-clock timeout (5min), token budget; no production AI agent ships without these
- Gateway starts and routes messages — prerequisite for all downstream features
- All 4 LLM providers working — users choose providers; all declared but not validated end-to-end
- Permission system session-scoped — current design is a privilege escalation bug
- SQL comment stripping — DML safety check is bypassable
- df_transform sandbox hardening — `type` builtin enables full sandbox escape
- Session persistence round-trip — tool call history lost on resume
- VarRegistry reporting all variable types — chart variables invisible to TUI and hibernation

**Should have (differentiators — add after v1 is stable):**
- Streaming output — users expect token-by-token display; waiting for full responses reads as frozen
- Session Memory extraction — the biggest differentiator; MemoryManager API exists, wiring does not
- Feishu adapter end-to-end validation — primary enterprise channel target; webhook architecture is correct but untested
- Hibernation async performance — Parquet writes block event loop; wrap in `asyncio.to_thread()`
- Forecast frequency explicit error — silent "ME" fallback produces wrong forecasts with no notice

**Defer (v2+):**
- Auto Dream consolidation — requires working Session Memory first; stub currently burns threshold for no value
- Teams adapter — requires async response rework (Outgoing Webhooks timeout at 10s for real queries)
- Google Chat adapter — requires same async pattern as Feishu; synchronous path times out
- spawn_agent real implementation — mark as preview; currently returns fake results
- Voice/Whisper — WhisperProvider raises NotImplementedError unconditionally; remove or gate
- Report scheduling (APScheduler) — schedules stored in-memory; disappear on restart; needs persistent job store

**Anti-features to address now (stubs claiming success):**
- spawn_agent, auto_dream, report_schedule, WhisperProvider — all return success or silently fail; must return clear error messages or be gated behind feature flags before shipping

### Architecture Approach

The three-tier architecture (Input Surfaces → Gateway Daemon → Agent Core) is the correct Unified Agent Gateway pattern for this domain. The AgentLoop is stateless; SessionContext is the mutable per-session state. The Gateway owns session lifecycle via SessionRegistry and ManagedSession with per-session `asyncio.Lock` for concurrency. The WebSocket protocol between Gateway and TUI has 13 well-typed message types (5 client-to-server, 8 server-to-client). The Feishu channel adapter correctly implements the 3-second ACK + background processing + card update pattern.

**Major components:**
1. AgentLoop (`agent.py`) — LLM-tool cycle; stateless; all channels flow through here via `run(input, ctx)`
2. GatewayServer (`gateway/server.py`) — FastAPI daemon; owns WebSocket connections, webhook routes, session routing
3. SessionRegistry (`gateway/session_registry.py`) — session CRUD, idle eviction, hibernate/restore dispatch
4. SessionHibernator (`gateway/hibernation.py`) — Parquet + JSONL + JSON serialization of session state to disk
5. GatewayWSClient + YigthinkerTUI (`tui/`) — Textual app with WebSocket client; exponential backoff reconnection
6. ChannelAdapters (`channels/`) — Feishu (implemented), Teams and Google Chat (stubs needing async rework)
7. MemoryManager + AutoDream (`memory/`) — cross-session knowledge extraction; wiring incomplete

**Key patterns to follow:**
- Per-session `asyncio.Lock` for write operations; lock-free reads for vars list and session info
- `asyncio.to_thread()` for all CPU-bound and sync I/O operations (Parquet writes, df_transform exec)
- `App.post_message()` / `call_from_thread()` in TUI for all widget updates from WebSocket worker context
- Store `asyncio.Task` references in a `set()` with `done_callback` discard (prevent GC of fire-and-forget tasks)
- Build gateway and CLI from shared `builder.py`, not from `__main__.py`

### Critical Pitfalls

1. **`asyncio.run()` inside Gateway event loop** — `_build()` uses `asyncio.run(MCPLoader.load())` which raises `RuntimeError` under uvicorn; MCP tools silently missing. Fix: extract `_build()` to `builder.py` with async variant for gateway context.

2. **Shared PermissionSystem across sessions** — ALLOW_ALL from any user mutates the shared `_allow` list, granting permission to all sessions. Fix: immutable base policy + session-scoped permission overrides; never mutate shared state from AgentLoop.

3. **Fire-and-forget `asyncio.create_task()` garbage collected** — Feishu adapter creates background tasks with no stored reference; Python 3.12+ GC aggressively collects unreferenced tasks; messages silently lost. Fix: maintain `self._background_tasks: set[asyncio.Task]` with `done_callback` discard.

4. **Hibernation deletes files before confirming restore** — `SessionHibernator.load()` calls `_rmtree(session_dir)` then adds session to registry; crash between these steps loses data permanently. Fix: deferred cleanup pattern — mark as `.restored/`, clean up in background task.

5. **df_transform sandbox escape via `type` builtin** — `type(df).__mro__[-1].__subclasses__()` chain reaches unrestricted builtins. Fix: remove `type` from `_SAFE_BUILTINS`; add `__class__`, `__mro__`, `__subclasses__` to AST blocker.

6. **TUI widget updates from wrong thread context** — `_on_ws_message` directly calls widget methods from WebSocket worker callback; Textual requires UI mutations on main thread. Fix: use `self.post_message(WSDataReceived(data))` and handle in a main-thread message handler.

7. **Stubs returning success** — `spawn_agent`, `auto_dream`, `report_schedule` return success with no computation; LLM plans around capabilities that do not exist. Fix: all stubs must return clear "not available in this version" errors or be gated behind feature flags.

## Implications for Roadmap

Based on the strict dependency graph in the research, a 5-phase structure is recommended. The bottom-up build order is dictated by what everything else calls: the AgentLoop is called by everything, so it must work first.

### Phase 1: Agent Loop Stabilization and Infrastructure
**Rationale:** Every downstream component depends on `AgentLoop.run()`. The `_build()` async nesting bug prevents MCP tools from loading in gateway context. Stubs returning success erode user trust before launch. These are blocking defects, not enhancements. This phase has no external dependencies and can be verified entirely through the CLI REPL and unit tests.
**Delivers:** A working, safe, honest agent loop that can be tested in isolation; clean build infrastructure
**Addresses:**
- Extract `_build()` to `builder.py` (sync and async variants)
- Fix `asyncio.run()` nesting for MCP loading
- Add iteration limit (25), wall-clock timeout (5min), max token budget guardrails
- Fix session persistence round-trip (restore tool call history from JSONL)
- Fix permission system for session-scoping (immutable base + per-session overrides)
- Fix SQL comment-stripping for DML bypass
- Fix df_transform sandbox (`type` builtin removal + AST blockers)
- Fix VarRegistry to report all variable types
- Fix forecast frequency (explicit error instead of silent "ME" fallback)
- Mark all stubs as "not available" (spawn_agent, auto_dream, report_schedule, WhisperProvider)
- Fix pytest-asyncio version floor in `pyproject.toml` (>=1.0.0) and other loose pins
**Avoids:** Pitfalls 2, 3 (asyncio nesting, circular import), Pitfall 3 (permission escalation), Pitfall 7 (sandbox escape)
**Research flag:** Standard patterns — no additional research needed; all issues are codebase-specific defects with documented fixes.

### Phase 2: Gateway and Session Management
**Rationale:** The Gateway is the hub that all channels and the TUI connect to. It cannot be stabilized until the AgentLoop works correctly. Key reliability concerns (hibernation crash safety, event loop blocking, session lock contention) must be addressed before adding clients that depend on the Gateway behaving correctly.
**Delivers:** A production-reliable Gateway daemon with correct session lifecycle, hibernation, and concurrency
**Addresses:**
- `GatewayServer.start()` using `builder.py` async variant
- Session lock refactoring (lock-free reads for vars/info; write lock only for agent loop execution)
- Hibernation crash-safety fix (deferred `.restored/` cleanup pattern)
- Synchronous I/O blocking fix: wrap Parquet writes and df_transform in `asyncio.to_thread()`
- Feishu dedup: switch to aiosqlite; implement two-phase dedup status
- WebSocket broadcast backpressure (bounded queue per client; disconnect slow clients)
- Cross-session permission contamination verified by integration test
**Avoids:** Pitfall 6 (hibernation data loss), Pitfall 8 (lock contention), synchronous I/O blocking the event loop
**Research flag:** Standard patterns — asyncio.to_thread, read-write lock patterns, deferred cleanup are all well-documented. No additional research needed.

### Phase 3: TUI Client
**Rationale:** The TUI requires a running Gateway. Once the Gateway is stable, the TUI can be wired to a real WebSocket endpoint. The thread-safety pattern for Textual workers must be established before wiring live data, or widget corruption bugs will appear intermittently.
**Delivers:** A functional terminal UI: chat flow, vars panel showing all variable types, session switching, model picker
**Addresses:**
- Refactor `_on_ws_message` to use `self.post_message(WSDataReceived(data))` for thread safety
- Wire DataFrame vars panel to VarRegistry (all types, not just DataFrames)
- Implement session reattachment after WebSocket reconnection
- Add jitter to exponential backoff to prevent thundering herd
- Show "processing..." state when session lock is held (second message queuing)
- Basic chat flow end-to-end without streaming (ResponseDoneMsg is sufficient for MVP)
**Avoids:** Pitfall 5 (Textual thread-safety violations causing Heisenbug crashes)
**Research flag:** Standard patterns — Textual worker and post_message patterns are documented in official Textual guides. No additional research needed.

### Phase 4: Streaming and Channel Adapters
**Rationale:** Streaming enhances TUI UX but is not a functional blocker. Channel adapters (Feishu, then Teams, then Google Chat) depend on Gateway.handle_message() working correctly. Feishu is the most complete and the primary target; Teams and Google Chat need architectural rework for async response patterns. These can proceed in parallel once the Gateway is stable.
**Delivers:** Token-by-token streaming in TUI; Feishu end-to-end validated; Teams and Google Chat async patterns
**Addresses:**
- Wire `provider.stream()` through AgentLoop as async generator; emit TokenEvent, ToolCallEvent, DoneEvent
- Add `request_id` to TokenStreamMsg and intermediate protocol messages for correlation
- Feishu: store task references in `self._background_tasks` set (GC fix); validate end-to-end with real webhook
- Feishu: dedup two-phase status (processing/done); handle Feishu domain vs lark domain routing
- Teams: implement HMAC-SHA256 verification (security prerequisite before any deployment)
- Teams: switch to async card update pattern via Graph API; evaluate Azure Bot Service registration
- Google Chat: implement async messaging API response pattern (return ACK, then send result via spaces.messages.create)
- Google Chat: separate inbound and outbound rate limiting
**Avoids:** Pitfall 1 (fire-and-forget task GC), Pitfall 4 (Teams webhook timeout), Pitfall 7 (Feishu dedup race), Pitfall 9 (Google Chat synchronous timeout)
**Research flag:** Teams adapter needs research — whether to continue with Outgoing Webhooks (simple but limited) or migrate to Azure Bot Service registration (full async, complex) depends on adoption. Recommend `/gsd:research-phase` before Teams implementation to evaluate the Microsoft 365 Agents SDK Python GA status.

### Phase 5: Session Memory and Auto Dream
**Rationale:** Memory features are enhancement layers on top of a working system. MemoryManager has the full API; the missing pieces are: (1) wiring `record_turn()` into the AgentLoop, and (2) implementing the LLM extraction step in `_do_extract()`. Auto Dream depends on Session Memory producing real content. Smart Compaction already falls back to tail truncation if MEMORY.md is empty, so this phase enhances rather than unblocks other features.
**Delivers:** Cross-session knowledge accumulation that survives compaction; agent improves within a project over time
**Addresses:**
- Wire `MemoryManager.record_turn()` into AgentLoop (after each completed turn)
- Implement LLM-powered extraction step (read recent turns, extract facts, merge into MEMORY.md sections)
- Implement `AutoDream._do_dream()`: read session transcripts, consolidate into MEMORY.md via AgentLoop.run()
- Validate SmartCompact with real MEMORY.md content (confirm memory injection works correctly)
- No new dependencies required — LLM provider + JSONL reader + file I/O already present
**Avoids:** Stubs burning Auto Dream threshold without value (already fixed in Phase 1 by returning clear error)
**Research flag:** Standard patterns — the Markdown-file memory approach is intentionally simpler than Mem0/Mastra. No vector store research needed. The LLM extraction prompt design may need iteration; flag for validation during implementation.

### Phase Ordering Rationale

- **Strict dependency chain:** AgentLoop → Gateway → TUI → Streaming+Channels → Memory. Each tier calls the one below it. This is not an arbitrary ordering — it is the actual dependency graph.
- **Parallel after Phase 3:** Streaming (4a) and Channel Adapters (4b) are independent once the Gateway works. They can be assigned to parallel workstreams.
- **Memory is enhancement, not infrastructure:** Session Memory does not block any other feature. Deferring it to Phase 5 allows the team to validate the core product before investing in the differentiator.
- **Security before deployment:** Teams HMAC verification and the df_transform sandbox fix are prerequisites for any user-facing deployment. Both are in Phase 1 and Phase 4, respectively.
- **Stubs fixed in Phase 1:** All stubs that return success must be converted to explicit errors in Phase 1. Shipping stubs that lie about their capabilities undermines trust more than not having the feature.

### Research Flags

Phases needing deeper research during planning:
- **Phase 4 (Teams adapter):** The Microsoft 365 Agents SDK Python preview status changes frequently. Before implementing Teams beyond HMAC verification, check whether the SDK has reached GA. If yes, it may be the better path over Outgoing Webhooks. Use `/gsd:research-phase` for this decision.

Phases with standard patterns (skip additional research):
- **Phase 1 (Agent Loop):** All issues are codebase-specific defects. Fixes are documented in PITFALLS.md with code snippets.
- **Phase 2 (Gateway):** asyncio.to_thread, read-write locks, deferred file cleanup are well-established patterns with official documentation.
- **Phase 3 (TUI):** Textual worker and post_message patterns are in official Textual docs.
- **Phase 5 (Memory):** No new technology; the extraction prompt will need iteration but that is implementation work, not research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technology choices validated against current PyPI releases and official docs. Version pinning issues are concrete and verifiable. No speculative recommendations. |
| Features | HIGH | Competitor analysis cross-referenced with codebase audit. Feature priorities derived from concrete dependency graph. Anti-features documented with specific failure modes. |
| Architecture | HIGH | Architecture analysis based on direct codebase reading. All data flows traced through actual code paths. Component boundaries reflect real implementation state. |
| Pitfalls | HIGH | Each pitfall identified through codebase analysis with line-number references. Prevention strategies cross-referenced with official docs (Python asyncio, Textual, Teams, Feishu). |

**Overall confidence:** HIGH

### Gaps to Address

- **Teams integration model:** Whether Outgoing Webhooks or Azure Bot Service registration is the right v1 path for Teams depends on whether the Microsoft 365 Agents SDK Python has reached GA. This is a go/no-go decision that affects Phase 4 scope. Validate before Phase 4 planning.
- **Feishu domain routing:** The lark vs feishu.cn API domain routing based on app_id prefix needs validation against the specific enterprise Feishu/Lark configuration. Document which domain the target deployment uses.
- **LLM extraction prompt for Session Memory:** The quality of memory extraction depends on prompt engineering. No research finding tells us the right extraction prompt. This will require iteration during Phase 5 implementation. Flag for A/B testing.
- **Windows production deployment:** The CLAUDE.md context confirms Windows as the primary dev platform, but `uvloop` is unavailable on Windows and `os.chmod(0o600)` silently fails. The gateway token file protection issue needs a Windows-specific fix (icacls) before any Windows production deployment.

## Sources

### Primary (HIGH confidence)
- FastAPI releases and WebSocket docs — gateway server patterns, SSE support timeline
- Textual PyPI and Workers guide — TUI async worker patterns, thread safety
- websockets 16.x docs — client-side WebSocket patterns
- PyArrow 23.x install and Parquet guide — DataFrame serialization
- Python asyncio official docs — task GC warning, asyncio.to_thread patterns
- lark-oapi GitHub (larksuite/oapi-sdk-python) — Feishu SDK current release and callback handling
- MSAL Python docs and PyPI — Azure AD token acquisition
- Microsoft Teams outgoing webhook docs — HMAC verification, timeout constraints
- Google Chat webhook quickstart and Cards v2 — adapter implementation
- pytest-asyncio releases — v1.0 breaking change documentation
- Textual Heisenbug blog post — create_task GC and worker thread safety

### Secondary (MEDIUM confidence)
- Tellius: Best AI Data Analysis Agents 2026 — competitor feature landscape
- MGX: Cross-Session Agent Memory — memory system frameworks and patterns
- MatrixTrak: Why Agents Loop Forever — loop detection and iteration limits
- Authority Partners: AI Agent Guardrails Production Guide 2026 — production safety requirements
- Microsoft Teams SDK Evolution 2025 (voitanos.io) — ecosystem navigation, Agents SDK status
- AI agent cross-session memory patterns (Towards Data Science) — Markdown-file approach validation
- Streaming AI Agent with FastAPI (dev.to) — async generator streaming pattern

### Tertiary (LOW confidence)
- Microsoft 365 Agents SDK Python preview status — evolving rapidly; validate before Phase 4 Teams work
- Office 365 Connectors retirement timeline — retirement deadline was extended; verify current status before any Connector-based work

---
*Research completed: 2026-04-02*
*Ready for roadmap: yes*
