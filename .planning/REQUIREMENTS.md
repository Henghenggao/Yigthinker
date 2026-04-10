# Requirements: Yigthinker

**Defined:** 2026-04-02
**Updated:** 2026-04-10 (v1.1 milestone)
**Core Value:** A user can interact via CLI REPL, IM channels, or TUI connected to the Gateway, having AI-assisted data analysis conversations with tool calls — same agent, multiple surfaces. Repeatable analysis patterns become automated workflows deployed to RPA platforms.

## v1.0 Requirements (Validated)

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

### Spawn Agent

- [x] **SPAWN-01** through **SPAWN-20**: Context-isolated sub-agent execution with DataFrame sharing, tool access control, lifecycle management, hook/permission inheritance, transcript persistence, predefined agent types

## v1.1 Requirements

Requirements for Workflow & RPA Bridge milestone. Each maps to roadmap phases.

### Workflow Generation

- [x] **WFG-01**: workflow_generate tool creates self-contained Python scripts from step definitions with target selection (python/power_automate/uipath)
- [x] **WFG-02**: Generated scripts include checkpoint_utils.py with retry + self-healing callback wrapper
- [x] **WFG-03**: Jinja2 templates render target-specific scripts (base, power_automate, uipath) using SandboxedEnvironment
- [x] **WFG-04**: Workflow Registry stores versioned scripts at ~/.yigthinker/workflows/ with registry.json index and per-workflow manifest.json
- [x] **WFG-05**: Generated config.yaml uses vault:// placeholder references for credentials, never plaintext
- [x] **WFG-06**: workflow_generate supports `update_of` parameter for versioned updates; previous versions preserved
- [x] **WFG-07**: Registry operations use filelock + atomic os.replace() to prevent corruption

### Deployment

- [x] **DEP-01**: workflow_deploy local mode generates Windows Task Scheduler XML or crontab entry
- [x] **DEP-02**: workflow_deploy guided mode generates paste-ready artifacts (setup_guide.md, flow_import.zip, task_scheduler.xml, test_trigger.ps1) with IM-native step-by-step instructions
- [x] **DEP-03**: workflow_deploy auto mode returns structured next-step instructions for LLM to call MCP tools through normal AgentLoop cycle
- [x] **DEP-04**: LLM auto-selects deploy mode based on environment (MCP available → auto, PA/UiPath mentioned but no API → guided, no RPA → local); user can override
- [x] **DEP-05**: After deployment (any mode), metadata written to Workflow Registry (manifest.json + registry.json)

### Lifecycle Management

- [x] **LCM-01**: workflow_manage list action shows all workflows with status, version, schedule, last run
- [x] **LCM-02**: workflow_manage inspect action shows detailed manifest for a specific workflow
- [x] **LCM-03**: workflow_manage pause/resume actions control scheduled triggers
- [x] **LCM-04**: workflow_manage rollback action reverts to a previous version
- [x] **LCM-05**: workflow_manage retire action permanently deactivates a workflow (preserves files)
- [x] **LCM-06**: workflow_manage health_check action checks run health of all active workflows

### Gateway RPA Endpoints

- [ ] **GW-RPA-01**: /api/rpa/callback endpoint receives self-healing requests with Bearer token auth, returns fix_applied/skip/escalate decisions
- [ ] **GW-RPA-02**: /api/rpa/callback uses callback_id deduplication via sqlite3 (matching the EventDeduplicator pattern at `yigthinker/channels/feishu/dedup.py`)
- [ ] **GW-RPA-03**: /api/rpa/report endpoint accepts execution status reports (no LLM cost, pure data write)
- [ ] **GW-RPA-04**: Circuit breaker limits self-healing: 3 attempts per checkpoint per 24h, 10 LLM calls per workflow per day
- [x] **GW-RPA-05**: Generated scripts treat Gateway as optional — ConnectionError falls back to escalate

### Behavior Layer

- [ ] **BHV-01**: System prompt directive instructs LLM to evaluate tasks for automation potential after completing work
- [ ] **BHV-02**: SessionStart hook performs registry health check (failure rate, overdue executions) and injects alerts into context
- [x] **BHV-03**: Proactive suggestions include estimated time saved, execution frequency, and required connections
- [x] **BHV-04**: Declined suggestions stored in patterns.json (not registry.json) under suppressed_suggestions with pattern, reason, and 3-month expiry
- [ ] **BHV-05**: Cross-session pattern detection via AutoDream memory (same tool sequence in 2+ sessions flags as automation-worthy)

### MCP Server: UiPath

- [ ] **MCP-UI-01**: Independent package yigthinker-mcp-uipath with 5 tools: ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status
- [ ] **MCP-UI-02**: OAuth2 client credentials authentication (no API key path)
- [ ] **MCP-UI-03**: Configured via .mcp.json with vault:// environment variable references

### MCP Server: Power Automate

- [ ] **MCP-PA-01**: Independent package yigthinker-mcp-powerautomate with 5 tools: pa_deploy_flow, pa_trigger_flow, pa_flow_status, pa_pause_flow, pa_list_connections
- [ ] **MCP-PA-02**: MSAL ConfidentialClientApplication authentication
- [ ] **MCP-PA-03**: Configured via .mcp.json with vault:// environment variable references

## v2 Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Hibernation

- **HIB-01**: Session hibernation serializes DataFrames to Parquet, messages to JSONL
- **HIB-02**: Session restore loads hibernated state with crash-safe atomic operations
- **HIB-03**: Hibernation metadata includes version for forward compatibility

### Channel Adapters

- **FEISHU-01**: Feishu adapter receives webhook, returns ACK within 3 seconds
- **FEISHU-02**: Feishu adapter sends "thinking" card, updates same card with result
- **FEISHU-03**: Feishu event deduplication via SQLite-backed EventDeduplicator
- **GCHAT-01**: Google Chat adapter authenticates via Service Account
- **GCHAT-02**: Google Chat adapter sends Cards v2 responses
- **GCHAT-03**: Google Chat adapter enforces per-space rate limiting

### Advanced Features

- **ADV-01**: Speculation engine predicts next user action and pre-computes responses
- **ADV-02**: Advisor dual-model PreToolUse hook for financial validation
- **ADV-03**: Voice/Whisper integration for speech-to-text input

## Out of Scope

| Feature | Reason |
|---------|--------|
| Visual workflow editor | Headless product — users don't see scripts |
| Built-in cron scheduler | OS Task Scheduler / PA / UiPath handles scheduling |
| Screen recording / macro recording | AI-driven generation, not a recorder |
| RPA platforms beyond PA + UiPath | Start with two, validate pattern, then expand |
| Real-time script preview | Test run after generation is sufficient |
| Runtime dependency on Yigthinker | Scripts must be self-contained |
| Require API access for deployment | guided mode works with zero API access |
| Speculation/prediction engine | High complexity, requires stable core first |
| Advisor dual-model architecture | Requires stable core + proven Session Memory |
| Voice/Whisper integration | WhisperProvider fundamentally broken |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LOOP-01 through LOOP-09 | Phase 1 (v1.0) | Complete |
| GW-01 through GW-06 | Phase 2 (v1.0) | Complete |
| TUI-01 through TUI-07 | Phase 3 (v1.0) | Complete |
| STRM-01 through STRM-04 | Phase 4 (v1.0) | Complete |
| TEAMS-01 through TEAMS-03 | Phase 4 (v1.0) | Complete |
| MEM-01 through MEM-04 | Phase 5 (v1.0) | Complete |
| SPAWN-01 through SPAWN-20 | Phase 7 (v1.0) | Complete |
| WFG-01 | Phase 8 | Complete |
| WFG-02 | Phase 8 | Complete |
| WFG-03 | Phase 8 | Complete |
| WFG-04 | Phase 8 | Complete |
| WFG-05 | Phase 8 | Complete |
| WFG-06 | Phase 8 | Complete |
| WFG-07 | Phase 8 | Complete |
| GW-RPA-05 | Phase 8 | Complete |
| DEP-01 | Phase 9 | Complete |
| DEP-02 | Phase 9 | Complete |
| DEP-03 | Phase 9 | Complete |
| DEP-04 | Phase 9 | Complete |
| DEP-05 | Phase 9 | Complete |
| LCM-01 | Phase 9 | Complete |
| LCM-02 | Phase 9 | Complete |
| LCM-03 | Phase 9 | Complete |
| LCM-04 | Phase 9 | Complete |
| LCM-05 | Phase 9 | Complete |
| LCM-06 | Phase 9 | Complete |
| GW-RPA-01 | Phase 10 | Pending |
| GW-RPA-02 | Phase 10 | Pending |
| GW-RPA-03 | Phase 10 | Pending |
| GW-RPA-04 | Phase 10 | Pending |
| BHV-01 | Phase 10 | Pending |
| BHV-02 | Phase 10 | Pending |
| BHV-03 | Phase 10 | Complete |
| BHV-04 | Phase 10 | Complete |
| BHV-05 | Phase 10 | Pending |
| MCP-UI-01 | Phase 11 | Pending |
| MCP-UI-02 | Phase 11 | Pending |
| MCP-UI-03 | Phase 11 | Pending |
| MCP-PA-01 | Phase 12 | Pending |
| MCP-PA-02 | Phase 12 | Pending |
| MCP-PA-03 | Phase 12 | Pending |

**Coverage:**
- v1.0 requirements: 53 total (all complete)
- v1.1 requirements: 34 total
- Mapped to phases: 34/34
- Unmapped: 0

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-10 after v1.1 roadmap creation*
