# Roadmap: Yigthinker

## Milestones

- [v1.0 Stabilization](milestones/v1.0-ROADMAP.md) - Phases 1-7 (shipped 2026-04-08)
- [v1.1 Workflow & RPA Bridge](milestones/v1.1-ROADMAP.md) - Phases 8-12 (shipped 2026-04-12)

## Phases

<details>
<summary>v1.0 Stabilization (Phases 1-7) - SHIPPED 2026-04-08</summary>

- [x] **Phase 1: Agent Loop & Infrastructure** - Fix the core LLM-tool cycle so it runs end-to-end with all 4 providers
- [x] **Phase 2: Gateway & Sessions** - Stand up the daemon that routes messages and manages session lifecycle
- [x] **Phase 3: TUI Client** - Wire the terminal UI to the Gateway for interactive data analysis conversations
- [x] **Phase 4: Streaming & Teams Adapter** - Add token-by-token streaming and Teams channel integration
- [x] **Phase 5: Session Memory & Auto Dream** - Enable cross-session knowledge accumulation
- [x] **Phase 7: Spawn Agent** - Context-isolated sub-agent execution with DataFrame sharing and lifecycle management

See [v1.0 archive](milestones/v1.0-ROADMAP.md) for full phase details.

</details>

<details>
<summary>v1.1 Workflow & RPA Bridge (Phases 8-12) - SHIPPED 2026-04-12</summary>

- [x] **Phase 8: Workflow Foundation** - Registry, templates, and workflow_generate tool with versioning and security
- [x] **Phase 9: Deployment & Lifecycle** - workflow_deploy (local/guided/auto) and workflow_manage (7 lifecycle actions)
- [x] **Phase 10: Gateway RPA & Behavior Layer** - Self-healing endpoints, status reporting, proactive automation suggestions, cross-session pattern detection
- [x] **Phase 11: UiPath MCP Server** - Independent yigthinker-mcp-uipath package with OAuth2 and 5 tools
- [x] **Phase 12: Power Automate MCP Server** - Independent yigthinker-mcp-powerautomate package with MSAL auth and 5 tools

See [v1.1 archive](milestones/v1.1-ROADMAP.md) for full phase details and plan listings.

</details>

## Progress

| Milestone | Phases | Plans | Status | Shipped |
|-----------|--------|-------|--------|---------|
| v1.0 Stabilization | 6 | 18 | Complete | 2026-04-08 |
| v1.1 Workflow & RPA Bridge | 5 | 26 | Complete | 2026-04-12 |
