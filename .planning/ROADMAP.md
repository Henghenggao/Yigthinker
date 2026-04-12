# Roadmap: Yigthinker

## Milestones

- v1.0 Stabilization - Phases 1-7 (shipped 2026-04-08)
- v1.1 Workflow & RPA Bridge - Phases 8-12 (in progress)

## Phases

<details>
<summary>v1.0 Stabilization (Phases 1-7) - SHIPPED 2026-04-08</summary>

- [x] **Phase 1: Agent Loop & Infrastructure** - Fix the core LLM-tool cycle so it runs end-to-end with all 4 providers
- [x] **Phase 2: Gateway & Sessions** - Stand up the daemon that routes messages and manages session lifecycle
- [x] **Phase 3: TUI Client** - Wire the terminal UI to the Gateway for interactive data analysis conversations
- [x] **Phase 4: Streaming & Teams Adapter** - Add token-by-token streaming and Teams channel integration
- [x] **Phase 5: Session Memory & Auto Dream** - Enable cross-session knowledge accumulation
- [x] **Phase 7: Spawn Agent** - Context-isolated sub-agent execution with DataFrame sharing and lifecycle management

### Phase 1: Agent Loop & Infrastructure
**Goal**: A user can start the CLI, have a multi-turn conversation with any of the 4 LLM providers, use tools, and get honest results
**Depends on**: Nothing (first phase)
**Requirements**: LOOP-01, LOOP-02, LOOP-03, LOOP-04, LOOP-05, LOOP-06, LOOP-07, LOOP-08, LOOP-09
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md -- Session infrastructure: typed VarRegistry + ContextManager injection
- [x] 01-02-PLAN.md -- AgentLoop guardrails: iteration limit, timeout, session-scoped permissions
- [x] 01-03-PLAN.md -- Builder extraction: async build_app, MCP fail-fast, honest stub tools
- [x] 01-04-PLAN.md -- Downstream fixes: chart tools migration, ctx.context_manager, provider tests, sandbox hardening

### Phase 2: Gateway & Sessions
**Goal**: A user can start the Gateway daemon and interact with it over WebSocket
**Depends on**: Phase 1
**Requirements**: GW-01, GW-02, GW-03, GW-04, GW-05, GW-06
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Core integration: fix build_app ask_fn, server.py _build import, gateway CLI command
- [x] 02-02-PLAN.md -- Test verification: health, concurrency, and WebSocket e2e tests

### Phase 3: TUI Client
**Goal**: A user can open the TUI, connect to a running Gateway, have a conversation, see DataFrame variables, switch sessions, and navigate with keyboard shortcuts
**Depends on**: Phase 2
**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-05, TUI-06, TUI-07
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md -- Core TUI wiring: CLI entry, ChatLog markdown, picker screens, InputBar autocomplete, DataFrame preview
- [x] 03-02-PLAN.md -- Gateway tool callback, ToolCard collapse/expand, TUI test suite

### Phase 4: Streaming & Teams Adapter
**Goal**: Users see tokens appear incrementally in the TUI as the LLM generates them, and Teams users can interact with the agent via webhook
**Depends on**: Phase 3
**Requirements**: STRM-01, STRM-02, STRM-03, STRM-04, TEAMS-01, TEAMS-02, TEAMS-03
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md -- StreamEvent type, provider stream() methods, AgentLoop on_token callback integration
- [x] 04-02-PLAN.md -- Teams HMAC-SHA256 verification, Adaptive Cards webhook, session key derivation
- [x] 04-03-PLAN.md -- Gateway TokenStreamMsg broadcast, TUI MarkdownStream rendering, streaming tests

### Phase 5: Session Memory & Auto Dream
**Goal**: The agent remembers key findings within a session and accumulates domain knowledge across sessions
**Depends on**: Phase 1, Phase 2
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md -- LLM extraction in MemoryManager + LLM consolidation in AutoDream
- [x] 05-02-PLAN.md -- AgentLoop lifecycle wiring, builder hook registration, system prompt injection

### Phase 7: Spawn Agent
**Goal**: The LLM can delegate subtasks to child agent loops that execute in isolation
**Depends on**: Phase 1, Phase 5
**Requirements**: SPAWN-01 through SPAWN-20
**Plans**: 5 plans

Plans:
- [x] 07-01-PLAN.md -- SubAgent engine: child AgentLoop factory, isolated SessionContext, context isolation
- [x] 07-02-PLAN.md -- DataFrame sharing: copy-in by name, merge-back with prefix
- [x] 07-03-PLAN.md -- Tool access control: allowed_tools whitelist, spawn_agent recursion removal
- [x] 07-04-PLAN.md -- Lifecycle management: foreground/background modes, concurrency limiter, agent_status/agent_cancel
- [x] 07-05-PLAN.md -- Integration: hook/permission inheritance, Gateway broadcast, TUI display, predefined agent types

</details>

### v1.1 Workflow & RPA Bridge (In Progress)

**Milestone Goal:** Enable Yigthinker to recognize repeatable analysis patterns and proactively generate, deploy, and manage automated workflows on mainstream RPA platforms.

- [x] **Phase 8: Workflow Foundation** - Registry, templates, and workflow_generate tool with versioning and security
- [x] **Phase 9: Deployment & Lifecycle** - workflow_deploy (local/guided/auto) and workflow_manage (list/inspect/pause/resume/rollback/retire/health)
- [x] **Phase 10: Gateway RPA & Behavior Layer** - Self-healing endpoints, status reporting, proactive automation suggestions, and cross-session pattern detection (completed 2026-04-11)
- [x] **Phase 11: UiPath MCP Server** - Independent yigthinker-mcp-uipath package with OAuth2 and 5 tools (completed 2026-04-11)
- [x] **Phase 12: Power Automate MCP Server** - Independent yigthinker-mcp-powerautomate package with MSAL auth and 5 tools (completed 2026-04-12)

## Phase Details

### Phase 8: Workflow Foundation
**Goal**: The agent can generate versioned, self-contained Python scripts from analysis step definitions, stored in a file-based registry with atomic operations and credential safety
**Depends on**: Phase 7 (v1.0 complete -- stable Agent Loop with all tools)
**Requirements**: WFG-01, WFG-02, WFG-03, WFG-04, WFG-05, WFG-06, WFG-07, GW-RPA-05
**Success Criteria** (what must be TRUE):
  1. User asks the agent to automate an analysis task and receives a generated Python script that can run standalone without Yigthinker installed
  2. Generated scripts include checkpoint/retry logic and treat Gateway self-healing as optional (ConnectionError falls back gracefully)
  3. Workflow Registry at ~/.yigthinker/workflows/ stores versioned scripts with manifest.json and registry.json; previous versions are preserved on update
  4. Generated config.yaml files use vault:// placeholders for credentials -- no plaintext secrets appear in any generated artifact
  5. Concurrent registry writes from multiple sessions do not corrupt files (filelock + atomic os.replace)
**Plans**: 3 plans

Plans:
- [x] 08-01-PLAN.md -- WorkflowRegistry: versioned file storage with filelock + atomic writes
- [x] 08-02-PLAN.md -- Jinja2 templates: inheritance chain, SandboxedEnvironment, AST validation
- [ ] 08-03-PLAN.md -- workflow_generate tool: step rendering, from_history, registry wiring

### Phase 9: Deployment & Lifecycle
**Goal**: Users can deploy generated workflows to local OS schedulers or RPA platforms and manage their full lifecycle -- from active scheduling through rollback to retirement
**Depends on**: Phase 8
**Requirements**: DEP-01, DEP-02, DEP-03, DEP-04, DEP-05, LCM-01, LCM-02, LCM-03, LCM-04, LCM-05, LCM-06
**Success Criteria** (what must be TRUE):
  1. User can deploy a workflow locally and get a working Windows Task Scheduler XML or crontab entry ready for installation
  2. User in guided mode receives paste-ready artifacts (setup_guide.md, flow_import.zip, task_scheduler.xml, test_trigger.ps1) with step-by-step IM-native instructions
  3. In auto mode, the agent returns structured next-step instructions and calls MCP tools through the normal AgentLoop cycle (no direct tool-to-tool calls)
  4. User can list all workflows with status/version/schedule/last-run, inspect a specific workflow's manifest, pause/resume triggers, rollback to a previous version, and retire a workflow
  5. After any deployment (local, guided, or auto), metadata is written to the Workflow Registry (manifest.json + registry.json updated)
**Plans**: TBD

### Phase 10: Gateway RPA & Behavior Layer
**Goal**: Running workflows can call back to Yigthinker for AI-assisted self-healing on failure, and the agent proactively recognizes repeatable analysis patterns and suggests automation
**Depends on**: Phase 8 (Registry for health checks), Phase 9 (deployed workflows for callbacks)
**Requirements**: GW-RPA-01, GW-RPA-02, GW-RPA-03, GW-RPA-04, BHV-01, BHV-02, BHV-03, BHV-04, BHV-05
**Success Criteria** (what must be TRUE):
  1. A running script hits a checkpoint failure and POSTs to /api/rpa/callback; the Gateway authenticates via Bearer token, deduplicates via callback_id, and returns a fix_applied/skip/escalate decision
  2. Circuit breaker enforces limits: max 3 self-healing attempts per checkpoint per 24 hours, max 10 LLM calls per workflow per day
  3. Scripts POST execution status to /api/rpa/report and the Gateway records it without incurring LLM cost
  4. After the agent completes a data analysis task, it evaluates the task for automation potential and suggests workflows with estimated time saved, frequency, and required connections
  5. Cross-session pattern detection flags tool sequences repeated in 2+ sessions as automation-worthy; declined suggestions are stored with 3-month expiry and not re-suggested
**Plans**: 4 plans
  - [x] 10-01-PLAN.md -- Gateway RPA endpoints + sqlite state store + circuit breaker (Wave 1)
  - [x] 10-02-PLAN.md -- Extraction-only LLM callback + prompt parsing (Wave 2, depends on 10-01)
  - [x] 10-03-PLAN.md -- PatternStore + suggest_automation tool + behavior gate (Wave 1)
  - [x] 10-04-PLAN.md -- Behavior Layer wiring: BHV-01 directive + BHV-02 startup alerts + BHV-05 AutoDream pattern extraction (Wave 2, depends on 10-01 + 10-03)

### Phase 11: UiPath MCP Server
**Goal**: Users with UiPath Orchestrator can auto-deploy workflows via a standalone MCP server package that Yigthinker calls through the standard MCP protocol
**Depends on**: Phase 9 (auto deploy mode calls MCP tools)
**Requirements**: MCP-UI-01, MCP-UI-02, MCP-UI-03
**Success Criteria** (what must be TRUE):
  1. yigthinker-mcp-uipath is an independent pip-installable package with 5 tools (ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status) accessible via stdio MCP protocol
  2. Authentication uses OAuth2 client credentials exclusively (no API key path); credentials referenced via vault:// in .mcp.json
  3. The agent in auto deploy mode can call UiPath MCP tools to deploy a generated workflow, trigger a test job, and verify deployment status -- all through the normal AgentLoop cycle
**Plans**: 8 plans

Plans:
- [x] 11-01-PLAN.md -- Package scaffold: pyproject, module stubs, conftest fixtures, scaffold smoke test (Wave 0)
- [x] 11-02-PLAN.md -- UipathAuth: OAuth2 client credentials with space-separated scopes, asyncio.Lock refresh guard (Wave 1, depends on 11-01)
- [x] 11-03-PLAN.md -- OrchestratorClient: 10 OData wrappers, 3-retry backoff, folder header, InputArguments JSON string (Wave 1, depends on 11-01)
- [x] 11-04-PLAN.md -- build_nupkg: stdlib zipfile with operate.json + entry-points.json + nuspec + psmdcp templates (Wave 1, depends on 11-01)
- [x] 11-05-PLAN.md -- 5 tool handlers: ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status + TOOL_REGISTRY (Wave 2, depends on 11-02 + 11-03 + 11-04)
- [x] 11-06-PLAN.md -- MCP low-level Server wiring + stdio smoke test + UipathConfig env loader (Wave 3, depends on 11-05)
- [x] 11-07-PLAN.md -- Core drift cleanup: fix mcp_detection identifiers + add rpa-uipath extra + grep drift guard (Wave 3, depends on 11-05)
- [x] 11-08-PLAN.md -- Package README with install, config, tools, troubleshooting (Wave 4, depends on 11-06 + 11-07)

### Phase 12: Power Automate MCP Server
**Goal**: Users with Microsoft Power Automate can auto-deploy workflows via a standalone MCP server package using MSAL authentication
**Depends on**: Phase 9 (auto deploy mode calls MCP tools)
**Requirements**: MCP-PA-01, MCP-PA-02, MCP-PA-03
**Success Criteria** (what must be TRUE):
  1. yigthinker-mcp-powerautomate is an independent pip-installable package with 5 tools (pa_deploy_flow, pa_trigger_flow, pa_flow_status, pa_pause_flow, pa_list_connections) accessible via stdio MCP protocol
  2. Authentication uses MSAL ConfidentialClientApplication; credentials referenced via vault:// in .mcp.json
  3. The agent in auto deploy mode can call PA MCP tools to deploy a generated workflow as a Power Automate flow and verify it runs -- all through the normal AgentLoop cycle
**Plans**: 8 plans

Plans:
- [x] 12-01-PLAN.md -- Package scaffold: pyproject, module stubs, conftest fixtures, scaffold smoke test (Wave 0)
- [x] 12-02-PLAN.md -- PowerAutomateAuth: MSAL ConfidentialClientApplication with token caching, asyncio.Lock refresh guard (Wave 1, depends on 12-01)
- [x] 12-03-PLAN.md -- PowerAutomateClient: Flow Management API wrappers, 3-retry backoff, api-version param (Wave 1, depends on 12-01)
- [x] 12-04-PLAN.md -- build_notification_flow_clientdata: HTTP Trigger + Send Email V2 template (Wave 1, depends on 12-01)
- [x] 12-05-PLAN.md -- 5 tool handlers: pa_deploy_flow, pa_trigger_flow, pa_flow_status, pa_pause_flow, pa_list_connections + TOOL_REGISTRY (Wave 2, depends on 12-02 + 12-03 + 12-04)
- [x] 12-06-PLAN.md -- MCP low-level Server wiring + stdio smoke test + PowerAutomateConfig env loader (Wave 3, depends on 12-05)
- [x] 12-07-PLAN.md -- Core drift cleanup: fix mcp_detection PA identifiers + add rpa-pa extra + extend drift guard (Wave 3, depends on 12-05)
- [x] 12-08-PLAN.md -- Package README with install, config, tools, troubleshooting (Wave 4, depends on 12-06 + 12-07)

## Progress

**Execution Order:**
Phases execute in numeric order: 8 -> 9 -> 10 -> 11 -> 12

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Agent Loop & Infrastructure | v1.0 | 4/4 | Complete | 2026-04-02 |
| 2. Gateway & Sessions | v1.0 | 2/2 | Complete | 2026-04-03 |
| 3. TUI Client | v1.0 | 2/2 | Complete | 2026-04-03 |
| 4. Streaming & Teams Adapter | v1.0 | 3/3 | Complete | 2026-04-05 |
| 5. Session Memory & Auto Dream | v1.0 | 2/2 | Complete | 2026-04-06 |
| 7. Spawn Agent | v1.0 | 5/5 | Complete | 2026-04-08 |
| 8. Workflow Foundation | v1.1 | 0/3 | Planned    |  |
| 9. Deployment & Lifecycle | v1.1 | 0/TBD | Not started | - |
| 10. Gateway RPA & Behavior Layer | v1.1 | 4/4 | Complete    | 2026-04-11 |
| 11. UiPath MCP Server | v1.1 | 8/8 | Complete   | 2026-04-11 |
| 12. Power Automate MCP Server | v1.1 | 8/8 | Complete   | 2026-04-12 |
