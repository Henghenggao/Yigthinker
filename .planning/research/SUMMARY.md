# Project Research Summary

> **Status:** Pre-implementation research for v1.1. v1.1 shipped 2026-04-12. This document is a historical reference — consult shipped code and phase summaries for current state.

**Project:** Yigthinker v1.1 — Workflow & RPA Bridge
**Domain:** Workflow generation, RPA deployment, self-healing, and proactive automation
**Researched:** 2026-04-09
**Confidence:** HIGH (core loop), MEDIUM (MCP server API specifics)

## Executive Summary

Yigthinker v1.1 adds a workflow/RPA bridge that converts ad-hoc financial analysis conversations into deployable, scheduled automations. The LLM already observed the analysis steps — it can generate a self-contained Python script that reproduces them without manual workflow composition. The architecture extends Yigthinker with three new tools, a file-based workflow registry, two Gateway endpoints, and optional independent MCP server packages for Power Automate and UiPath. Only 6 existing files require modification; everything else is additive.

## Stack Additions

| Addition | Version | Purpose |
|----------|---------|---------|
| jinja2 | >=3.1.6 | Template rendering for script generation (CVE-2025-27516 fix) |
| croniter | >=6.0.0 | Cron expression parsing/validation for schedules |
| filelock | (existing) | Registry file locking (already in deps) |

**MCP server packages (independent):**
- `yigthinker-mcp-uipath`: `mcp + httpx` (lighter, mature API)
- `yigthinker-mcp-powerautomate`: `mcp + httpx + msal`, optional `[azure]` extra for `azure-mgmt-web`

**Do NOT add:** `api.flow.microsoft.com` SDK (unsupported), `uipath` official SDK (scope mismatch), `nuget` CLI (stdlib zipfile suffices)

## Feature Table Stakes

| Feature | Category | Notes |
|---------|----------|-------|
| Script generation from step definitions | Table stakes | workflow_generate tool |
| Versioned workflow storage | Table stakes | Registry with manifest.json |
| List/inspect workflows | Table stakes | workflow_manage |
| Local execution mode | Table stakes | Task Scheduler XML / crontab |
| Checkpoint/retry | Table stakes | checkpoint_utils.py template |
| Config separation (credentials, connections) | Table stakes | config.yaml with vault:// refs |
| Pause/resume scheduled triggers | Table stakes | workflow_manage |
| Rollback to previous version | Table stakes | workflow_manage |

## Key Differentiators

1. **Conversation-to-workflow** — No competitor converts a data analysis conversation directly into a deployed automation. n8n/Zapier require manual composition.
2. **Three-tier deploy model** — `auto` (API), `guided` (paste-ready), `local` (OS scheduler). `guided` is the most important mode — largest real-world user segment.
3. **Self-healing callbacks** — Scripts call back to Yigthinker on failure for AI-assisted diagnosis. Gateway-optional.
4. **Proactive automation suggestions** — LLM recognizes repeatable patterns and suggests automation after completing tasks.

## Architecture Integration

- **6 existing files modified** (1-15 lines each): agent.py, server.py, types.py, pyproject.toml, settings.py, hooks/__init__.py
- **Everything else is additive** — new tools/, hooks/, gateway/ modules, templates/
- **Build order:** Registry → Templates → Tools → Behavior Wiring → Gateway Endpoints → MCP Servers → E2E
- **WorkflowRegistry is process-scoped** — workflows outlive sessions
- **Tools must NOT call other tools directly** — workflow_deploy auto mode returns structured instructions; LLM calls MCP tools through normal AgentLoop cycle

## Watch Out For

| Pitfall | Severity | Prevention |
|---------|----------|------------|
| Jinja2 SSTI from LLM-supplied params | CRITICAL | SandboxedEnvironment + AST check on output |
| Credential leakage in generated configs | CRITICAL | vault:// defaults + .gitignore + scanner |
| Callback auth bypass | CRITICAL | Bearer token (reuse GatewayAuth) |
| Registry file corruption | HIGH | filelock + atomic os.replace() + .bak |
| Unbounded self-healing LLM costs | HIGH | Circuit breaker (3 attempts/checkpoint/24h, 10 LLM calls/workflow/day) |
| PA Flow API unreliability | MODERATE | Use Dataverse Web API for simple flows; Azure Functions for compute |
| UiPath API key deprecation (March 2025) | MODERATE | OAuth2 only, no API key path |
| Windows Task Scheduler Python paths | LOW | Absolute paths in generated XML |

## Suggested Phases

1. **Foundation** — Registry, templates, workflow_generate (security baked in)
2. **Deployment & Lifecycle** — workflow_deploy (local + guided), workflow_manage, Gateway endpoints
3. **Behavior Layer** — System prompt, health check hook, proactive suggestions, decline memory
4. **UiPath Auto-Deploy MCP** — Independent package, validates MCP pattern (OData API mature)
5. **PA Auto-Deploy MCP** — Independent package, deferred due to PA API fragility

## Research Flags

- Phase 4 needs `/gsd:research-phase`: UiPath .nupkg Python Activity schema
- Phase 5 needs `/gsd:research-phase`: PA Dataverse `clientdata` payload, Azure Function deployment

---
*Synthesized: 2026-04-10 from STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
