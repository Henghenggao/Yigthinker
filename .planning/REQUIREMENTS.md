# Requirements: Yigthinker

**Defined:** 2026-04-02
**Core Value:** A user can start the Gateway, open the TUI, have an AI-assisted data analysis conversation with tool calls, and see results — with the same experience accessible from messaging platforms.

## v1 Requirements

Requirements for stabilization milestone. Each maps to roadmap phases.

### Agent Loop & Infrastructure

- [x] **LOOP-01**: Agent Loop executes full cycle: LLM call -> tool_use parse -> PreToolUse hooks -> execute -> PostToolUse hooks -> tool_result -> loop
- [x] **LOOP-02**: ClaudeProvider completes chat() and returns valid tool_use/text responses
- [x] **LOOP-03**: OpenAIProvider completes chat() and returns valid tool_use/text responses
- [x] **LOOP-04**: OllamaProvider completes chat() and returns valid tool_use/text responses
- [x] **LOOP-05**: AzureProvider completes chat() and returns valid tool_use/text responses
- [x] **LOOP-06**: _build() does not use nested asyncio.run(); MCP tools load correctly in async context
- [x] **LOOP-07**: Agent Loop enforces iteration limit (configurable, default 50)
- [x] **LOOP-08**: Agent Loop enforces per-turn timeout (configurable, default 300s)
- [x] **LOOP-09**: Stub tools (spawn_agent) return clear "not implemented" errors, not fake success

### Gateway & Sessions

- [x] **GW-01**: Gateway starts on configurable host:port, serves /health endpoint returning {"status":"ok"}
- [x] **GW-02**: WebSocket endpoint accepts auth + attach + user_input messages per protocol spec
- [x] **GW-03**: SessionRegistry creates, retrieves, and lists sessions with metadata
- [x] **GW-04**: Per-session asyncio.Lock serializes concurrent access to same session
- [x] **GW-05**: Session scoping works: per-sender, per-channel, named, global key derivation
- [x] **GW-06**: Idle session eviction runs on configurable interval and respects max_sessions

### TUI Client

- [x] **TUI-01**: TUI connects to Gateway via WebSocket and displays chat log with markdown rendering
- [x] **TUI-02**: VarsPanel shows current session's DataFrame variables with name, shape, and dtypes
- [x] **TUI-03**: Keyboard shortcuts work: Ctrl+G (sessions), Ctrl+L (models), Ctrl+D (preview), Ctrl+Q (quit)
- [x] **TUI-04**: WebSocket reconnection with exponential backoff (1s base, 30s max)
- [x] **TUI-05**: StatusBar shows connection state (green connected, yellow reconnecting, red disconnected)
- [x] **TUI-06**: ToolCard widgets display tool calls with collapsible detail (Ctrl+O toggle)
- [x] **TUI-07**: InputBar supports slash command autocomplete with tab completion

### Streaming

- [x] **STRM-01**: LLM providers expose stream() method returning AsyncIterator[StreamEvent]
- [x] **STRM-02**: AgentLoop propagates streaming events through callback or async generator
- [x] **STRM-03**: Gateway broadcasts token stream events to subscribed WebSocket clients
- [x] **STRM-04**: TUI renders tokens incrementally as they arrive in ChatLog widget

### Teams Adapter

- [x] **TEAMS-01**: Teams adapter receives webhook POST with HMAC-SHA256 signature verification
- [x] **TEAMS-02**: Teams adapter sends response via Graph API with Adaptive Cards formatting
- [x] **TEAMS-03**: Teams adapter derives session key from sender identity using SessionKey pattern

### Memory

- [x] **MEM-01**: Session Memory records key findings after each tool call via MemoryManager.record_turn()
- [x] **MEM-02**: Session Memory survives context compaction via PreCompact hook injection
- [x] **MEM-03**: Auto Dream triggers at SessionEnd, extracts domain knowledge via LLM summarization
- [x] **MEM-04**: Auto Dream persists memories to ~/.yigthinker/memory/, loaded at SessionStart

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Hibernation

- **HIB-01**: Session hibernation serializes DataFrames to Parquet, messages to JSONL
- **HIB-02**: Session restore loads hibernated state with crash-safe atomic operations
- **HIB-03**: Hibernation metadata includes version for forward compatibility

### Feishu Adapter

- **FEISHU-01**: Feishu adapter receives webhook, returns ACK within 3 seconds
- **FEISHU-02**: Feishu adapter sends "thinking" card, updates same card with result
- **FEISHU-03**: Feishu event deduplication via SQLite-backed EventDeduplicator

### Google Chat Adapter

- **GCHAT-01**: Google Chat adapter authenticates via Service Account
- **GCHAT-02**: Google Chat adapter sends Cards v2 responses
- **GCHAT-03**: Google Chat adapter enforces per-space rate limiting (1 req/sec)

### Advanced Features

- **ADV-01**: Speculation engine predicts next user action and pre-computes responses
- **ADV-02**: Advisor dual-model PreToolUse hook for financial validation
- **ADV-03**: Voice/Whisper integration for speech-to-text input

## Out of Scope

| Feature | Reason |
|---------|--------|
| Speculation/prediction engine | High complexity, requires stable core first |
| Advisor dual-model architecture | Requires stable core + proven Session Memory |
| Voice/Whisper integration | WhisperProvider fundamentally broken, defer |
| APScheduler report scheduling | Enterprise feature, no scheduler implemented |
| Real HashiCorp Vault integration | Env var alias sufficient for current scale |
| Mobile app | Web/TUI first |
| OAuth login for Gateway | Token auth sufficient for local/team use |
| Feishu adapter | Deferred to v2 -- prioritize Teams for this milestone |
| Google Chat adapter | Deferred to v2 -- limited to Workspace users only |
| Session hibernation | Deferred to v2 -- focus on core loop stability first |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LOOP-01 | Phase 1 | Complete |
| LOOP-02 | Phase 1 | Complete |
| LOOP-03 | Phase 1 | Complete |
| LOOP-04 | Phase 1 | Complete |
| LOOP-05 | Phase 1 | Complete |
| LOOP-06 | Phase 1 | Complete |
| LOOP-07 | Phase 1 | Complete |
| LOOP-08 | Phase 1 | Complete |
| LOOP-09 | Phase 1 | Complete |
| GW-01 | Phase 2 | Complete |
| GW-02 | Phase 2 | Complete |
| GW-03 | Phase 2 | Complete |
| GW-04 | Phase 2 | Complete |
| GW-05 | Phase 2 | Complete |
| GW-06 | Phase 2 | Complete |
| TUI-01 | Phase 3 | Complete |
| TUI-02 | Phase 3 | Complete |
| TUI-03 | Phase 3 | Complete |
| TUI-04 | Phase 3 | Complete |
| TUI-05 | Phase 3 | Complete |
| TUI-06 | Phase 3 | Complete |
| TUI-07 | Phase 3 | Complete |
| STRM-01 | Phase 4 | Complete |
| STRM-02 | Phase 4 | Complete |
| STRM-03 | Phase 4 | Complete |
| STRM-04 | Phase 4 | Complete |
| TEAMS-01 | Phase 4 | Complete |
| TEAMS-02 | Phase 4 | Complete |
| TEAMS-03 | Phase 4 | Complete |
| MEM-01 | Phase 5 | Complete |
| MEM-02 | Phase 5 | Complete |
| MEM-03 | Phase 5 | Complete |
| MEM-04 | Phase 5 | Complete |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-02 after roadmap creation*
