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

### Spawn Agent (Sub-Agent Parallel Execution)

Design adapted from Claude Code's sub-agent architecture. Core principles: context isolation (intermediate
tool calls never enter parent messages), least-privilege tool access, recursion prevention, and
DataFrame sharing as Yigthinker's domain-specific extension.

#### Context Isolation & Execution

- **SPAWN-01**: spawn_agent creates a child AgentLoop with an isolated SessionContext and independent message history; the child does NOT receive the parent's conversation history
- **SPAWN-02**: Only the child's **final text message** (end_turn) is returned to the parent as the tool_result; intermediate tool calls and tool_results stay inside the child and never enter the parent's messages
- **SPAWN-03**: The child AgentLoop uses the same or overridden LLM provider (per `model` parameter: None=inherit, or explicit provider name)

#### DataFrame Sharing (Yigthinker-specific)

- **SPAWN-04**: Specified DataFrames (`dataframes: list[str]`) are shallow-copied from parent ctx.vars to child ctx.vars before execution; unspecified parent DataFrames are not visible to the child
- **SPAWN-05**: New or modified DataFrames created by the child are merged back into parent ctx.vars after completion, with a `{agent_name}_` prefix to prevent name collisions (e.g. child's `df1` becomes `east_df1` in parent)
- **SPAWN-06**: The merge-back summary (which DataFrames were added/modified, their shapes) is appended to the tool_result text so the parent LLM is aware of new data

#### Tool Access Control

- **SPAWN-07**: spawn_agent accepts an optional `allowed_tools: list[str]` parameter; when set, the child ToolRegistry contains ONLY those tools (principle of least privilege)
- **SPAWN-08**: When `allowed_tools` is omitted, the child inherits all parent tools EXCEPT `spawn_agent` itself (recursion prevention — subagents cannot spawn subagents)
- **SPAWN-09**: The child's ToolRegistry is built at spawn time and is immutable for the child's lifetime

#### Lifecycle Management

- **SPAWN-10**: Foreground mode (default, `background=False`): spawn_agent awaits the child AgentLoop.run() and returns the result inline as a single tool_result
- **SPAWN-11**: Background mode (`background=True`): spawn_agent launches the child as an asyncio.Task, returns immediately with a `subagent_id`, and the parent continues its own loop
- **SPAWN-12**: Concurrent subagent limit is configurable via settings (`spawn_agent.max_concurrent`, default 3); excess spawns return a clear error to the LLM for replanning
- **SPAWN-13**: agent_status companion tool lists all subagents (running/completed/failed) with their subagent_id, name, status, and elapsed time
- **SPAWN-14**: agent_cancel companion tool cancels a running background subagent by subagent_id; the cancelled subagent's partial results (if any) are discarded

#### Hook & Permission Inheritance

- **SPAWN-15**: The child inherits the parent's HookExecutor and PermissionSystem references; child tool calls fire PreToolUse/PostToolUse hooks normally under the parent's session_id
- **SPAWN-16**: A new `SubagentStop` hook event fires when a child completes (or is cancelled), carrying `subagent_id`, `subagent_name`, `final_text`, and `status` (completed/failed/cancelled)

#### Transcript & Observability

- **SPAWN-17**: Each subagent's conversation is persisted as a separate JSONL transcript at `~/.yigthinker/sessions/subagents/{session_id}/{subagent_id}.jsonl`
- **SPAWN-18**: Gateway broadcasts subagent lifecycle events (spawned/completed/failed) to attached WebSocket clients so the dashboard and TUI can display subagent status

#### Predefined Agent Types (Extension)

- **SPAWN-19**: `.yigthinker/agents/*.md` files with YAML frontmatter (`name`, `description`, `allowed_tools`, `model`) define reusable agent types; spawn_agent accepts an optional `agent_type: str` that loads the predefined prompt and tool restrictions
- **SPAWN-20**: When `agent_type` is set, the predefined agent's `description` and system prompt are injected into the child's context; user-provided `prompt` becomes the task instruction appended after the system prompt

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
| SPAWN-01 | Phase 7 | Not Started |
| SPAWN-02 | Phase 7 | Not Started |
| SPAWN-03 | Phase 7 | Not Started |
| SPAWN-04 | Phase 7 | Not Started |
| SPAWN-05 | Phase 7 | Not Started |
| SPAWN-06 | Phase 7 | Not Started |
| SPAWN-07 | Phase 7 | Not Started |
| SPAWN-08 | Phase 7 | Not Started |
| SPAWN-09 | Phase 7 | Not Started |
| SPAWN-10 | Phase 7 | Not Started |
| SPAWN-11 | Phase 7 | Not Started |
| SPAWN-12 | Phase 7 | Not Started |
| SPAWN-13 | Phase 7 | Not Started |
| SPAWN-14 | Phase 7 | Not Started |
| SPAWN-15 | Phase 7 | Not Started |
| SPAWN-16 | Phase 7 | Not Started |
| SPAWN-17 | Phase 7 | Not Started |
| SPAWN-18 | Phase 7 | Not Started |
| SPAWN-19 | Phase 7 | Not Started |
| SPAWN-20 | Phase 7 | Not Started |

**Coverage:**
- v1 requirements: 33 total, all mapped
- v1.1 requirements: 20 total (SPAWN-01 through SPAWN-20)
- Mapped to phases: 53
- Unmapped: 0

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-08 after expanding Phase 7 with Claude Code design principles*
