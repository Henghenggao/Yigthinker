# Roadmap: Yigthinker Stabilization

## Overview

This milestone takes a heavily scaffolded but largely non-functional codebase and makes it work end-to-end. The build order follows the strict dependency chain: the Agent Loop is called by everything else, so it must work first. The Gateway depends on a working Agent Loop. The TUI depends on a working Gateway. Streaming and channel adapters enhance what the Gateway delivers. Memory features layer on top of a working system. Each phase delivers a coherent, independently verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Agent Loop & Infrastructure** - Fix the core LLM-tool cycle so it runs end-to-end with all 4 providers
- [x] **Phase 2: Gateway & Sessions** - Stand up the daemon that routes messages and manages session lifecycle
- [x] **Phase 3: TUI Client** - Wire the terminal UI to the Gateway for interactive data analysis conversations
- [ ] **Phase 4: Streaming & Teams Adapter** - Add token-by-token streaming and Teams channel integration
- [ ] **Phase 5: Session Memory & Auto Dream** - Enable cross-session knowledge accumulation

## Phase Details

### Phase 1: Agent Loop & Infrastructure
**Goal**: A user can start the CLI, have a multi-turn conversation with any of the 4 LLM providers, use tools, and get honest results -- with no silent failures, no stubs pretending to work, and no safety bypasses
**Depends on**: Nothing (first phase)
**Requirements**: LOOP-01, LOOP-02, LOOP-03, LOOP-04, LOOP-05, LOOP-06, LOOP-07, LOOP-08, LOOP-09
**Success Criteria** (what must be TRUE):
  1. User can start the CLI, send a prompt, and receive an LLM response that includes tool calls executing real tools -- with Claude, OpenAI, Ollama, and Azure providers
  2. Agent Loop stops itself after hitting the iteration limit or timeout instead of looping forever
  3. Stub tools (spawn_agent) return a clear "not available" error instead of fake success
  4. MCP tools load correctly without asyncio.run() nesting errors, both in CLI and when imported by Gateway
  5. All existing tests pass
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md -- Session infrastructure: typed VarRegistry + ContextManager injection
- [x] 01-02-PLAN.md -- AgentLoop guardrails: iteration limit, timeout, session-scoped permissions
- [x] 01-03-PLAN.md -- Builder extraction: async build_app, MCP fail-fast, honest stub tools
- [ ] 01-04-PLAN.md -- Downstream fixes: chart tools migration, ctx.context_manager, provider tests, sandbox hardening

### Phase 2: Gateway & Sessions
**Goal**: A user can start the Gateway daemon and interact with it over WebSocket -- sessions are created, routed, scoped, and evicted correctly
**Depends on**: Phase 1
**Requirements**: GW-01, GW-02, GW-03, GW-04, GW-05, GW-06
**Success Criteria** (what must be TRUE):
  1. Gateway starts on a configurable host:port and responds to /health with {"status":"ok"}
  2. A WebSocket client can authenticate, attach to a session, send user input, and receive the agent's response
  3. Two concurrent WebSocket messages to the same session are serialized (not interleaved) by the per-session lock
  4. Sessions are scoped correctly: per-sender, per-channel, named, and global keys produce distinct sessions
  5. Idle sessions are evicted after the configured interval, and max_sessions is respected
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Core integration: fix build_app ask_fn, server.py _build import, gateway CLI command
- [x] 02-02-PLAN.md -- Test verification: health, concurrency, and WebSocket e2e tests

### Phase 3: TUI Client
**Goal**: A user can open the TUI, connect to a running Gateway, have a conversation, see DataFrame variables, switch sessions, and navigate with keyboard shortcuts
**Depends on**: Phase 2
**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-05, TUI-06, TUI-07
**Success Criteria** (what must be TRUE):
  1. TUI connects to the Gateway and displays a chat log with markdown rendering of the conversation
  2. VarsPanel shows the current session's variables (DataFrames and chart JSON) with name, shape, and dtypes
  3. Keyboard shortcuts work: Ctrl+G opens session list, Ctrl+L opens model picker, Ctrl+D opens preview, Ctrl+Q quits
  4. When the WebSocket disconnects, the TUI reconnects automatically with exponential backoff and the StatusBar reflects connection state (green/yellow/red)
  5. Tool calls display as collapsible ToolCard widgets with Ctrl+O toggle
**Plans**: 2 plans
**UI hint**: yes

Plans:
- [x] 03-01-PLAN.md -- Core TUI wiring: CLI entry, ChatLog markdown, picker screens, InputBar autocomplete, DataFrame preview
- [x] 03-02-PLAN.md -- Gateway tool callback, ToolCard collapse/expand, TUI test suite

### Phase 4: Streaming & Teams Adapter
**Goal**: Users see tokens appear incrementally in the TUI as the LLM generates them, and Teams users can interact with the agent via webhook
**Depends on**: Phase 3 (streaming requires TUI for rendering; Teams requires Gateway for routing)
**Requirements**: STRM-01, STRM-02, STRM-03, STRM-04, TEAMS-01, TEAMS-02, TEAMS-03
**Success Criteria** (what must be TRUE):
  1. LLM responses stream token-by-token into the TUI ChatLog widget instead of appearing all at once
  2. Streaming works end-to-end: provider stream() -> AgentLoop events -> Gateway WebSocket broadcast -> TUI incremental render
  3. Teams adapter receives a webhook POST, verifies the HMAC-SHA256 signature, and rejects invalid signatures
  4. Teams adapter sends a response back via Graph API with Adaptive Cards formatting
  5. Teams adapter derives a session key from sender identity so each user gets their own session
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md -- StreamEvent type, provider stream() methods, AgentLoop on_token callback integration
- [x] 04-02-PLAN.md -- Teams HMAC-SHA256 verification, Adaptive Cards webhook, session key derivation
- [x] 04-03-PLAN.md -- Gateway TokenStreamMsg broadcast, TUI MarkdownStream rendering, streaming tests

### Phase 5: Session Memory & Auto Dream
**Goal**: The agent remembers key findings within a session (surviving context compaction) and accumulates domain knowledge across sessions
**Depends on**: Phase 1 (Agent Loop for extraction), Phase 2 (Gateway for SessionEnd hook)
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04
**Success Criteria** (what must be TRUE):
  1. After a tool call produces a key finding, MemoryManager.record_turn() captures it without user intervention
  2. When context compaction occurs, session memories are injected into the compacted context via PreCompact hook -- the agent retains knowledge of earlier findings
  3. When a session ends, Auto Dream extracts domain knowledge via LLM summarization and persists it to ~/.yigthinker/memory/
  4. On the next session start, previously dreamed memories are loaded and available to the agent
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md -- LLM extraction in MemoryManager + LLM consolidation in AutoDream
- [ ] 05-02-PLAN.md -- AgentLoop lifecycle wiring, builder hook registration, system prompt injection

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Agent Loop & Infrastructure | 4/4 | Complete | 2026-04-02 |
| 2. Gateway & Sessions | 2/2 | Complete | 2026-04-03 |
| 3. TUI Client | 2/2 | Complete | 2026-04-03 |
| 4. Streaming & Teams Adapter | 3/3 | Complete | 2026-04-05 |
| 5. Session Memory & Auto Dream | 1/2 | In Progress |  |
