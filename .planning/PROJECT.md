# Yigthinker

## What This Is

Yigthinker is a Python-based AI agent for financial and data analysis — a headless "data analysis Claude Code" with multi-channel access. It uses a flat tool registry (26 tools), a single Agent Loop, hooks for cross-cutting concerns, and in-memory DataFrame operations. The codebase includes Gateway daemon, Textual TUI, and channel adapters (Teams integrated; Feishu/Google Chat deferred). Core loop, Gateway, TUI, streaming, memory, and spawn agent are all functional.

## Core Value

A user can interact via CLI REPL, IM channels (Teams), or TUI connected to the Gateway, having AI-assisted data analysis conversations with tool calls (SQL, DataFrame, charts, forecasts, finance calculations) — same agent, multiple surfaces.

## Current Milestone: v1.1 Workflow & RPA Bridge

**Goal:** Enable Yigthinker to recognize repeatable analysis patterns and proactively generate, deploy, and manage automated workflows on mainstream RPA platforms.

**Target features:**
- 3 new native tools: workflow_generate, workflow_deploy, workflow_manage
- Workflow Registry with versioned scripts, manifests, and run history
- "Automate everything" behavior layer with proactive suggestions
- Gateway RPA endpoints for self-healing and status reporting
- 2 MCP server packages: yigthinker-mcp-powerautomate and yigthinker-mcp-uipath
- Generated Python scripts with checkpoint/retry/self-healing structure
- 3 deploy modes: auto, guided, local

## Requirements

### Validated

- ✓ Project structure and module layout — existing
- ✓ 26 tool definitions with Pydantic schemas — existing + finance tools
- ✓ LLM provider abstraction (Claude, OpenAI, Ollama, Azure) — existing
- ✓ Hook system (PreToolUse, PostToolUse, SessionStart, SessionEnd, etc.) — existing
- ✓ Permission system (allow/ask/deny pattern matching) — existing
- ✓ SessionContext with VarRegistry for DataFrames — existing
- ✓ Settings system (project + user + managed layers) — existing
- ✓ MCP integration for external tools — existing
- ✓ Plugin system with YAML frontmatter commands — existing
- ✓ Session persistence as JSONL transcripts — existing
- ✓ Agent Loop runs end-to-end — Validated in Phase 1
- ✓ CLI REPL functional with all 4 LLM providers — Validated in Phase 1
- ✓ Fix nested asyncio.run() in __main__.py _build() — Validated in Phase 1
- ✓ Fix VarRegistry.list() to include non-DataFrame variables — Validated in Phase 1
- ✓ Fix ContextManager instantiation — Validated in Phase 1
- ✓ Wire spawn_agent to honest error — Validated in Phase 1
- ✓ All existing tests pass — Validated in Phase 1
- ✓ Gateway daemon starts, manages multi-session via WebSocket/HTTP API — Validated in Phase 2
- ✓ Session scoping (per-sender, per-channel, named, global) — Validated in Phase 2
- ✓ Session hibernation/restore (DataFrame → Parquet, messages → JSONL) — Validated in Phase 2
- ✓ TUI connects to Gateway, chat log with markdown rendering — Validated in Phase 3
- ✓ TUI VarsPanel, keyboard shortcuts, reconnection, ToolCards — Validated in Phase 3
- ✓ LLM streaming (provider → AgentLoop → Gateway → TUI) — Validated in Phase 4
- ✓ Teams adapter (HMAC verification, Adaptive Cards, session keys) — Validated in Phase 4
- ✓ Session Memory (key findings, survives compaction) — Validated in Phase 5
- ✓ Auto Dream (SessionEnd extraction, cross-session persistence) — Validated in Phase 5
- ✓ Spawn Agent (context isolation, DataFrame sharing, tool access control, lifecycle) — Validated in Phase 7
- ✓ 4 finance tools (calculate, analyze, validate, budget) — Validated post-Phase 5
- ✓ workflow_generate tool: generate self-contained Python scripts from step definitions — Validated in Phase 8
- ✓ Workflow Registry: versioned scripts, manifests at ~/.yigthinker/workflows/ — Validated in Phase 8
- ✓ Jinja2 templates for Python/PA/UiPath script generation (SandboxedEnvironment) — Validated in Phase 8
- ✓ checkpoint_utils.py template: retry + self-healing callback wrapper (Gateway optional) — Validated in Phase 8

### Active

- [ ] workflow_deploy tool: deploy to RPA platforms with auto/guided/local modes
- [ ] workflow_manage tool: list/inspect/pause/resume/rollback/retire/health_check
- [ ] "Automate everything" behavior: system prompt directive + proactive suggestions
- [ ] SessionStart hook: registry health check on conversation start
- [ ] Gateway /api/rpa/callback: self-healing endpoint for failed checkpoints
- [ ] Gateway /api/rpa/report: status reporting (no LLM cost)
- [ ] yigthinker-mcp-powerautomate: independent MCP server package (5 tools)
- [ ] yigthinker-mcp-uipath: independent MCP server package (5 tools)

### Out of Scope

- Speculation/prediction engine — complex feature, defer to future milestone
- Advisor dual-model architecture — requires stable core first
- Voice/Whisper integration — WhisperProvider is broken, defer
- APScheduler for report scheduling — enterprise feature, defer
- Real HashiCorp Vault integration — env var alias sufficient for now
- Mobile app — web/TUI first
- OAuth login for Gateway — token auth sufficient
- Visual workflow editor — headless product, users don't see scripts
- Built-in cron scheduler — OS Task Scheduler / PA / UiPath handles scheduling
- Screen recording / macro recording — AI-driven generation, not a recorder
- RPA platforms beyond PA + UiPath at launch — start with two, validate pattern first
- Real-time script preview — test run after generation is sufficient

## Context

**Brownfield project:** Extensive codebase (~60+ Python files) with a fully functional core. Agent Loop, Gateway, TUI, streaming, memory, spawn agent, and workflow generation are all working end-to-end. 550 tests passing.

**Design spec:** Workflow & RPA Bridge design at `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md` defines the full architecture: native tools, registry, behavior layer, gateway endpoints, MCP servers, and generated script structure.

**Key design principles:**
- Yigthinker is the architect, not the executor — generates automation, doesn't run it
- AI intervenes only on exception — 100 daily RPA runs, maybe 1 calls back to Yigthinker
- Scripts are self-contained — Gateway unavailability only disables self-healing
- Code-level output for auditability, but non-technical users never see code
- 3 deploy modes accommodate different infrastructure levels (full API → paste-ready → local only)

**Key technical facts:**
- AgentLoop is stateless — `run(user_input, ctx)` operates on passed SessionContext
- One AgentLoop instance can serve unlimited concurrent sessions
- Gateway maintains `session_key → ManagedSession` mapping with per-session asyncio.Lock
- MCP servers are independent packages communicating via stdio protocol
- Workflow Registry is file-based (JSON) at `~/.yigthinker/workflows/`

## Constraints

- **Tech stack**: Python 3.11, existing dependencies + Jinja2 for templates
- **Platform**: Must work on Windows (no fork(), gateway runs foreground with --fg)
- **MCP independence**: MCP server packages are separate repos/packages, not bundled
- **Self-contained scripts**: Generated scripts must run without Yigthinker installed
- **Gateway optional**: Scripts must function with Gateway offline (lose self-healing only)
- **All 4 providers**: Claude, OpenAI, Ollama, Azure must all work with workflow tools

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Bottom-up stabilization order | TUI depends on Gateway, Gateway depends on Agent Loop | ✓ Good |
| Debug all 4 LLM providers | User wants full provider coverage | ✓ Good |
| Session Memory + Auto Dream in scope | User selected from brainstorm features | ✓ Good |
| Skip Speculation and Advisor | Too complex for stabilization milestone | ✓ Good |
| Teams via Graph API, not Bot Framework SDK | SDK deprecated Dec 2025 | ✓ Good |
| Dashboard permanently removed | Headless product by design | ✓ Good |
| Spawn Agent added to v1.0 | Enables parallel analysis workflows | ✓ Good |
| 4 finance tools ported from YCE | Calculate, analyze, validate, budget | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after Phase 8 Workflow Foundation complete*
