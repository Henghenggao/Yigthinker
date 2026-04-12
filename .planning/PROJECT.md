# Yigthinker

## What This Is

Yigthinker is a Python-based AI agent for financial and data analysis — a headless "data analysis Claude Code" with multi-channel access and workflow automation. It uses a flat tool registry (30 tools), a single Agent Loop, hooks for cross-cutting concerns, and in-memory DataFrame operations. The codebase includes Gateway daemon (with RPA self-healing endpoints), Textual TUI, channel adapters (Teams integrated with requirements coverage; Feishu/Google Chat adapters implemented but not yet formally validated with requirements), workflow generation/deployment/lifecycle management, and two independent MCP server packages for UiPath and Power Automate integration.

## Core Value

A user can interact via CLI REPL, IM channels (Teams), or TUI connected to the Gateway, having AI-assisted data analysis conversations with tool calls (SQL, DataFrame, charts, forecasts, finance calculations) — same agent, multiple surfaces. Repeatable analysis patterns become automated workflows deployed to RPA platforms (Power Automate, UiPath) or local OS schedulers.

## Shipped Milestones

### v1.1 Workflow & RPA Bridge (shipped 2026-04-12)

- 4 new native tools: workflow_generate, workflow_deploy, workflow_manage, suggest_automation
- Workflow Registry with versioned scripts, manifests, and run history
- "Automate everything" behavior layer with proactive suggestions and cross-session pattern detection
- Gateway RPA endpoints (/api/rpa/callback, /api/rpa/report) for self-healing and status reporting
- 2 MCP server packages: yigthinker-mcp-powerautomate (MSAL auth, 5 tools) and yigthinker-mcp-uipath (OAuth2, 5 tools)
- Generated Python scripts with checkpoint/retry/self-healing structure
- 3 deploy modes: auto (MCP), guided (paste-ready ZIP), local (OS scheduler)

### v1.0 Stabilization (shipped 2026-04-08)

- Agent Loop end-to-end with 4 LLM providers (Claude, OpenAI, Ollama, Azure)
- Gateway daemon with multi-session management, WebSocket API, session hibernation
- Textual TUI with markdown rendering, VarsPanel, keyboard shortcuts
- LLM token streaming through full stack (provider → AgentLoop → Gateway → TUI)
- Teams adapter with HMAC verification and Adaptive Cards
- Session Memory and Auto Dream cross-session knowledge accumulation
- Spawn Agent with context isolation, DataFrame sharing, tool access control

## Requirements

All v1.0 and v1.1 requirements shipped. See [v1.1 requirements archive](milestones/v1.1-REQUIREMENTS.md) for full traceability.

**Summary:** 87 requirements across 2 milestones — 53 (v1.0) + 34 (v1.1), all complete.

### Active

(No active requirements — next milestone not yet defined)

### Out of Scope

- Speculation/prediction engine — code exists behind `speculation` gate, defer formal validation to future milestone
- Advisor dual-model architecture — code exists behind `advisor` gate, requires stable core first
- Voice/Whisper integration — code exists behind `voice` gate, WhisperProvider is broken, defer
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

**Brownfield project:** Extensive codebase (~141 Python files across core + 2 independent MCP server packages) with all v1.0 and v1.1 features shipped. Agent Loop, Gateway (with RPA endpoints), TUI, streaming, memory, spawn agent, workflow generation/deployment/lifecycle, behavior layer, and both MCP server packages are all working end-to-end. ~680 tests passing across core + packages.

**Design specs:**
- Original design: `docs/superpowers/specs/2026-04-01-yigthinker-design.md`
- Workflow & RPA Bridge: `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md`

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
- PatternStore backs cross-session automation pattern detection with FileLock + lazy suppression pruning
- RPAStateStore uses synchronous sqlite3 (WAL mode) for callback dedup and circuit breaker state

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
| Architect-not-executor for workflow_deploy | Yigthinker never subprocess-execs schedulers or imports MCP; find_spec only | ✓ Good |
| Runtime ZIP bundle generation (no pre-canned artifacts) | Jinja2 + zipfile stdlib, rendered per-deploy | ✓ Good |
| Lazy-default-on-read for Phase 8→Phase 9 schema bump | No disk migration pass needed; per-entry merge on save preserves both | ✓ Good |
| Rolling back to currently-active version is an error | Loud-failure safer than silent no-op | ✓ Good |

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
*Last updated: 2026-04-12 — v1.1 Workflow & RPA Bridge milestone shipped, v1.0+v1.1 archived to milestones/*
