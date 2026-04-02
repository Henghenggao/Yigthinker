# Feature Research

**Domain:** AI-powered data analysis agent with multi-channel gateway access
**Researched:** 2026-04-02
**Confidence:** MEDIUM-HIGH

## Feature Landscape

This research covers two interlocking feature domains: (1) the AI data analysis agent core (tool execution, memory, session management) and (2) the multi-channel gateway layer (TUI, Feishu, Teams, Google Chat). The milestone focus is stabilization — making scaffolded code work end-to-end — not building net-new features.

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **End-to-end agent loop** | Users type a question, expect an answer. If tool calls silently fail or the loop never terminates, nothing else matters. | MEDIUM | Agent loop code exists but has no timeout/iteration limit and the nested `asyncio.run()` bug in `_build()` prevents MCP tools from loading. Fix these first. |
| **Streaming output** | Every major AI chat product (ChatGPT, Claude, Gemini) streams token-by-token. Users waiting 30+ seconds for a blank screen assume the app is frozen. | HIGH | `TokenStreamMsg` protocol type exists but `AgentLoop` uses `provider.chat()` not `provider.stream()`. Requires wiring streaming through agent loop, gateway WebSocket, and TUI. Industry consensus: streaming is table stakes for 2025+ AI products. |
| **Session persistence (basic)** | Users expect to close and reopen a conversation without losing work. JSONL transcript saving exists; session resume drops tool call entries. | LOW | `TranscriptReader.to_messages()` drops tool_result blocks on resume. Fix the message restoration to properly handle all message types. |
| **Multi-provider support** | Users choose their LLM provider. All 4 providers (Claude, OpenAI, Ollama, Azure) are declared but may not all work due to the `_build()` bug and untested edge cases. | MEDIUM | Test each provider's `chat()` path end-to-end. Provider abstraction is solid; the bugs are in bootstrapping and context construction. |
| **Permission system working correctly** | Users expect allow/ask/deny to work. Currently, `ALLOW_ALL` in one session contaminates all sessions via shared `PermissionSystem` mutation. | LOW | Fix by adding session-scoped permission overrides instead of mutating the shared `_allow` list. |
| **Agent loop safety guardrails** | Production AI agents need iteration limits, token budgets, and wall-clock timeouts. Without these, a misbehaving LLM burns API credits indefinitely. | MEDIUM | No iteration limit, no max token check, no timeout exists in `AgentLoop.run()`. Industry standard: 25 iterations max, 200K token budget, 5-minute wall-clock timeout. This is not optional for production. |
| **Gateway starts and serves sessions** | The gateway daemon is the hub for TUI and channels. If it cannot start, build tools, and route messages, nothing downstream works. | MEDIUM | `GatewayServer.start()` calls `_build()` from `__main__` (circular import risk, async nesting bug). Extract to `builder.py`. |
| **DataFrame variable registry for all types** | Users create charts, store DataFrames, run forecasts. `VarRegistry.list()` silently hides non-DataFrame vars (charts). | LOW | Extend `VarRegistry.list()` to report all variable types, not just DataFrames. Chart tools already store via `_vars` directly; formalize this. |
| **Correct frequency inference in forecasting** | Time series tools must handle daily, weekly, quarterly data. Silent fallback to month-end frequency produces wrong forecasts. | LOW | `ForecastTimeseriesTool` silently falls back to "ME" when `pd.infer_freq()` returns None. Either error explicitly or let the user specify frequency. |
| **SQL injection prevention** | `sql_query` DML check is bypassable via comment injection. For a financial data tool, SQL safety is non-negotiable. | LOW | Strip SQL comments before running the DML keyword regex check. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Session Memory (cross-turn extraction)** | Most AI data tools lose context when the conversation is compacted. Yigthinker's `MemoryManager` extracts key findings, data source knowledge, and error corrections into `MEMORY.md` — surviving compaction. This is the single biggest differentiator vs. PandasAI, Julius, etc. | HIGH | `MemoryManager` has full API but `record_turn()` is never called. Need to wire extraction into the agent loop and implement the actual LLM-powered extraction step. Mem0, AWS AgentCore, and Mastra all ship memory systems in 2025-2026; Yigthinker's markdown-file approach is simpler and more transparent. |
| **Auto Dream (cross-session knowledge consolidation)** | After enough sessions, automatically consolidate learnings into global memory. The agent gets smarter over time within a project, remembering table schemas, business rules, and past mistakes. | HIGH | `AutoDream._do_dream()` is a stub — acquires lock, updates state, but does no actual consolidation. Needs a real implementation that reads session transcripts and merges insights into MEMORY.md. Depends on Session Memory working first. |
| **Smart Compaction with memory injection** | When conversation exceeds token budget, inject extracted memory + recent messages instead of naive truncation. Preserves analytical continuity. | MEDIUM | `SmartCompact.run()` is implemented but depends on `MemoryManager` producing actual content. If MEMORY.md is template-only, falls back to tail truncation (generic, no differentiator). |
| **Multi-channel access (Feishu, Teams, Google Chat)** | Users interact with the same AI agent from their workplace messaging platform. Competitors require a separate web UI; Yigthinker meets users where they already are. | HIGH | Feishu adapter is the most complete (webhook, 3s ACK, card update pattern). Teams and Google Chat are stubs. CardRenderer protocol exists with per-platform rendering. The 3-second ACK + async processing + card update pattern is Feishu-specific and well-designed. |
| **TUI with DataFrame panel** | Terminal-native interface with live DataFrame variable display, session switching, model selection. Differentiated from web-only competitors for developers and data engineers who live in the terminal. | MEDIUM | TUI scaffolding is complete (Textual app, widgets, screens, WS client with exponential backoff). Needs wiring to a working gateway. DataFrame preview is explicitly marked "not wired yet." |
| **Session hibernation and restore** | Sessions can be serialized to disk (DataFrames as Parquet, messages as JSONL, stats as JSON) and restored later. Enables gateway restarts without losing user work. | LOW | `SessionHibernator` is fully implemented with save/load/manifest. The hibernation writes are synchronous in async context (performance issue, not correctness). Needs `asyncio.to_thread()` wrapping. |
| **Hook system for enterprise extensibility** | PreToolUse/PostToolUse hooks allow enterprises to add audit logging, RBAC, PII masking, approval workflows without modifying core code. Command hooks use exit codes (0=allow, 1=warn, 2=block). | LOW | Hook system is implemented and working. This is a differentiator for enterprise deployments. No changes needed for this milestone. |
| **`df_transform` sandboxed code execution** | Users write Python code that runs in a restricted `exec()` sandbox with only pandas/numpy/polars imports. Safer than competitors that allow arbitrary code execution. | LOW | Sandbox exists but has a CRITICAL escape vector via `type()` builtin. Remove `type` from `_SAFE_BUILTINS` and add `__class__`, `__mro__`, `__subclasses__` to the AST blocker. |
| **Platform-specific card rendering** | Rich output formatting adapted to each messaging platform (Feishu interactive cards, Teams Adaptive Cards, Google Chat Cards v2). DataFrame summaries, charts, and errors rendered natively. | MEDIUM | `CardRenderer` protocol defined with 5 methods. Feishu implementation exists. Teams and Google Chat need implementations. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Speculation/prediction engine** | Pre-compute likely next queries for faster response. Sounds like magic. | Adds massive complexity (prediction model, cache invalidation, resource management) for uncertain hit rates. The stub already exists and silently does nothing — worse than not having it. Hit/miss stats will always show 0. | Keep gated off. If desired later, implement as a PostToolUse hook that caches common follow-up queries, not a separate engine. |
| **Advisor dual-model architecture** | Use a cheap model for planning, expensive model for execution. Sounds cost-efficient. | Requires stable core first. Two-model coordination adds failure modes, latency, and complexity. The planner feature (off by default) partially covers this already. | Use the existing planner toggle for weak models. Dual-model routing is a future milestone after the agent loop is rock-solid. |
| **Voice/Whisper integration** | Voice input for hands-free data analysis. | `WhisperProvider._call_api()` raises `NotImplementedError` unconditionally. The voice gate exists but transcription always fails silently (returns ""). Ship it broken = erode trust. | Remove or clearly gate as "not available." Voice is a separate milestone after core works. |
| **APScheduler for report scheduling** | "Schedule this report to run weekly." | `report_schedule` stores entries in `ctx.settings` dict (in-memory, not persistent). Entries disappear on session end. No scheduler ever executes them. Claiming scheduled reports work when they don't is worse than not offering the feature. | Return a clear error message: "Report scheduling requires the enterprise scheduler (not available in this version)." Persist schedule entries to `.yigthinker/schedules.json` as a prerequisite for any future scheduler. |
| **Real HashiCorp Vault integration** | Secrets management for database credentials. | `vault://` resolution is just an env var lookup (`VAULT_*`). Implementing real Vault/AWS Secrets Manager is a large, separate effort. The current behavior is adequate for development. | Document the actual behavior (env var alias convention). Add a warning log when vault:// is used. Implement real vault in an enterprise milestone. |
| **`spawn_agent` multi-agent workflows** | Delegate sub-tasks to specialized agents. Sounds powerful. | `SpawnAgentTool._run_subagent()` returns a fake string summary. The LLM receives a successful-looking response with no actual computation. Silently broken multi-agent is worse than no multi-agent. | Mark tool description as `(preview - not functional)` and return a clear error. Implement when the core agent loop is proven stable. |
| **Real-time bidirectional streaming for all channels** | Streaming to Feishu/Teams/GChat like the TUI gets. | Messaging platforms use webhook-based request/response, not WebSockets. Feishu's card update pattern (send thinking card, PATCH with result) is the correct approach for async platforms. Trying to simulate streaming over webhooks adds complexity for minimal UX gain. | Use the async card update pattern (thinking -> result) for webhook-based channels. Reserve true streaming for WebSocket channels (TUI, future web UI). |

## Feature Dependencies

```
[Agent Loop end-to-end]
    |
    +--requires--> [asyncio.run() fix in _build()]
    |                  |
    |                  +--requires--> [Extract _build() to builder.py]
    |
    +--requires--> [Agent loop safety guardrails (timeout, iteration limit)]
    |
    +--enables---> [Gateway message routing]
    |                  |
    |                  +--enables---> [TUI chat functionality]
    |                  |
    |                  +--enables---> [Feishu adapter end-to-end]
    |                  |
    |                  +--enables---> [Teams adapter]
    |                  |
    |                  +--enables---> [Google Chat adapter]
    |
    +--enables---> [Streaming output]
                       |
                       +--enables---> [TUI token-by-token display]

[Session Memory extraction]
    |
    +--requires--> [Agent Loop end-to-end (to trigger record_turn)]
    |
    +--enables---> [Smart Compaction with memory]
    |
    +--enables---> [Auto Dream consolidation]
                       |
                       +--requires--> [Session Memory working]
                       +--requires--> [Multiple completed sessions with content]

[VarRegistry fix (all types)]
    |
    +--enables---> [TUI VarsPanel shows charts]
    +--enables---> [Hibernation manifest includes all vars]

[Permission system fix (session-scoped)]
    |
    +--requires--> [Gateway multi-session context]

[Session hibernation]
    |
    +--requires--> [Gateway running]
    +--enhances--> [Gateway restarts without data loss]
```

### Dependency Notes

- **Agent Loop is the critical path:** Every feature downstream depends on the agent loop running correctly. Fix `_build()`, add guardrails, verify end-to-end before touching gateway/TUI/channels.
- **Session Memory requires Agent Loop:** `MemoryManager.record_turn()` must be called from the agent loop. Memory extraction is an LLM call that requires the loop to work.
- **Auto Dream requires Session Memory:** Dream consolidation reads session transcripts and merges into MEMORY.md. If sessions have no extracted memory, there is nothing to consolidate.
- **TUI requires Gateway:** The TUI connects via WebSocket to the gateway. If the gateway cannot start, the TUI is a dead screen.
- **Channels require Gateway:** All channel adapters register webhook routes on the gateway's FastAPI app and call `gateway.handle_message()`.
- **Streaming enhances TUI but is not required for basic function:** The TUI can display `response_done` messages without streaming. Streaming is a UX improvement, not a functional blocker.

## MVP Definition

### Launch With (v1 - This Milestone)

Minimum viable: a user can start the gateway, open the TUI or send a Feishu message, ask a data analysis question, and get a correct answer with tool calls working.

- [ ] **Agent Loop end-to-end** — Fix `_build()` async nesting, extract to `builder.py`, add iteration limit (25) and wall-clock timeout (5min)
- [ ] **All 4 LLM providers working** — Test Claude, OpenAI, Ollama, Azure through the agent loop
- [ ] **Gateway starts and routes messages** — `GatewayServer.start()` works, sessions are created, messages are routed
- [ ] **TUI connects and displays responses** — Basic chat flow: user types, sees response. No streaming required for MVP.
- [ ] **VarRegistry lists all variable types** — Charts appear in vars panel alongside DataFrames
- [ ] **Session persistence round-trip** — Resume a session with tool call history intact
- [ ] **Permission system session-scoped** — ALLOW_ALL does not cross-contaminate sessions
- [ ] **SQL safety (comment stripping)** — DML check cannot be bypassed via comments
- [ ] **df_transform sandbox hardening** — Remove `type` from safe builtins, extend AST blocker

### Add After Validation (v1.x)

Features to add once core is working and the basic flow is validated.

- [ ] **Streaming output** — Wire `provider.stream()` through agent loop, gateway, and TUI. Trigger: users report the app "feels slow" due to waiting for full responses.
- [ ] **Session Memory extraction** — Wire `MemoryManager.record_turn()` into agent loop, implement LLM-powered extraction. Trigger: users lose context during long sessions due to compaction.
- [ ] **Feishu adapter end-to-end** — Validate 3s ACK, card update, event dedup with real Feishu webhook traffic. Trigger: Feishu is the primary enterprise channel for the target user base.
- [ ] **Hibernation async performance** — Wrap synchronous Parquet writes in `asyncio.to_thread()`. Trigger: large DataFrames block the event loop during hibernation.
- [ ] **Forecast frequency handling** — Error explicitly when frequency cannot be inferred, or accept user-specified frequency parameter. Trigger: users report wrong forecast dates.

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Auto Dream** — Requires Session Memory to be working and producing content. Defer until memory extraction is proven useful.
- [ ] **Teams adapter** — Graph API + httpx + msal integration. Defer until Feishu is stable and validated.
- [ ] **Google Chat adapter** — Service Account + Cards v2. Defer until at least one channel adapter is proven.
- [ ] **spawn_agent multi-agent** — Requires rock-solid single agent loop. Mark as preview until then.
- [ ] **Speculation engine** — Uncertain value. Keep gated off indefinitely.
- [ ] **Voice/Whisper** — Separate UX modality, separate milestone.
- [ ] **Report scheduling (APScheduler)** — Enterprise feature requiring persistent job store.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Agent Loop end-to-end (fix bugs) | HIGH | MEDIUM | P1 |
| Agent loop safety guardrails | HIGH | LOW | P1 |
| Gateway starts and routes | HIGH | MEDIUM | P1 |
| All 4 LLM providers working | HIGH | MEDIUM | P1 |
| VarRegistry all types | MEDIUM | LOW | P1 |
| Permission session-scoped fix | HIGH | LOW | P1 |
| SQL comment stripping | HIGH | LOW | P1 |
| df_transform sandbox hardening | HIGH | LOW | P1 |
| Session persistence round-trip | MEDIUM | LOW | P1 |
| TUI basic chat | HIGH | MEDIUM | P1 |
| Streaming output | HIGH | HIGH | P2 |
| Session Memory extraction | HIGH | HIGH | P2 |
| Feishu adapter validation | MEDIUM | MEDIUM | P2 |
| Hibernation async perf | LOW | LOW | P2 |
| Forecast frequency fix | MEDIUM | LOW | P2 |
| Auto Dream consolidation | MEDIUM | HIGH | P3 |
| Teams adapter | MEDIUM | HIGH | P3 |
| Google Chat adapter | MEDIUM | HIGH | P3 |
| spawn_agent real implementation | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for this milestone — bugs and blockers
- P2: Should have — validated differentiators
- P3: Nice to have — defer if time-constrained

## Competitor Feature Analysis

| Feature | PandasAI | Julius AI | Tableau Pulse | Querio | **Yigthinker** |
|---------|----------|-----------|---------------|--------|----------------|
| NL-to-SQL/Python | Yes | Yes | Yes | Yes | Yes (21 tools including sql_query, df_transform) |
| Multi-provider LLM | Partial (OpenAI, HuggingFace, Bedrock) | OpenAI only | Salesforce Einstein | Proprietary | Yes (Claude, OpenAI, Ollama, Azure) |
| Streaming output | Yes | Yes | N/A (dashboard) | N/A | Scaffolded, not wired |
| Cross-session memory | No | No | No | No | **Differentiator** (MemoryManager, Auto Dream) |
| Terminal TUI | No | No | No | No | **Differentiator** (Textual-based) |
| Enterprise messaging (Feishu/Teams/GChat) | No | No | Slack only | Slack only | **Differentiator** (3 platform adapters) |
| Hook system for enterprise extension | No | No | Proprietary | No | **Differentiator** (PreToolUse/PostToolUse hooks) |
| Sandboxed code execution | Partial | Yes | N/A | N/A | Yes (AST-restricted exec) |
| DataFrame hibernation (Parquet) | No | Cloud storage | N/A | N/A | Yes (local Parquet + manifest) |
| Session scoping (per-sender, per-channel) | N/A | N/A | N/A | N/A | **Differentiator** (SessionKey strategies) |
| Forecast tools | No | Basic | Yes (Tableau) | No | Yes (timeseries, regression, evaluate) |
| Plugin system | No | No | Tableau Extensions | No | Yes (YAML frontmatter commands, hooks, MCP) |

**Key insight from competitor analysis:** NL-to-query is table stakes in 2026. LLM-powered chatbot capabilities are commoditized. Yigthinker's differentiators are: (1) cross-session memory that accumulates domain knowledge, (2) multi-channel access from enterprise messaging platforms, (3) terminal-native TUI for developers, and (4) hook-based enterprise extensibility. None of these are offered by PandasAI, Julius, or the major BI platform chatbots.

## Sources

- [Tellius: Best AI Data Analysis Agents in 2026](https://www.tellius.com/resources/blog/best-ai-data-analysis-agents-in-2026-12-platforms-compared-for-nl-to-sql-autonomous-investigation-and-governance) — NL-to-query is table stakes, differentiator is what happens after
- [Anomaly AI: AI Data Analysis Trends 2026](https://www.findanomaly.ai/ai-data-analysis-trends-2026) — Speed and proactive insights as 2026 expectations
- [PandasAI GitHub](https://github.com/sinaptik-ai/pandas-ai) — Competitor feature reference
- [PandasAI Agent Docs](https://docs.pandas-ai.com/v3/agent) — Multi-turn conversations, sandboxed execution
- [MGX: Cross-Session Agent Memory](https://mgx.dev/insights/cross-session-agent-memory-foundations-implementations-challenges-and-future-directions/d03dd30038514b75ad4cbbda2239c468) — Memory system frameworks and patterns
- [Redis: AI Agent Memory Architecture](https://redis.io/blog/ai-agent-memory-stateful-systems/) — Memory types and implementation patterns
- [MachineLearningMastery: 6 Best AI Agent Memory Frameworks 2026](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/) — Mem0, AgentCore, Mastra memory systems
- [Ably: Reliable Resumable Token Streaming](https://ably.com/blog/token-streaming-for-ai-ux) — Streaming UX best practices
- [MatrixTrak: Why Agents Loop Forever](https://matrixtrak.com/blog/agents-loop-forever-how-to-stop) — Loop detection and timeout patterns
- [Skywork: Agentic AI Safety Best Practices 2025](https://skywork.ai/blog/agentic-ai-safety-best-practices-2025-enterprise/) — Guardrails and safety patterns
- [Authority Partners: AI Agent Guardrails Production Guide 2026](https://authoritypartners.com/insights/ai-agent-guardrails-production-guide-for-2026/) — Production safety requirements
- [ProProfsChat: Multichannel Chatbots Guide 2026](https://www.proprofschat.com/blog/multichannel-chatbot/) — Channel normalization patterns
- [Microsoft Learn: Teams Bots Overview](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/overview) — Teams bot architecture
- [Feishu Open Platform: Bot Overview](https://open.feishu.cn/document/client-docs/bot-v3/bot-overview) — Feishu bot capabilities and limits

---
*Feature research for: AI-powered data analysis agent with multi-channel gateway*
*Researched: 2026-04-02*
