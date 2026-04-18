# Changelog

All notable changes to Yigthinker are documented in this file.

## [Unreleased]

(No changes yet — 0.2.0 just released 2026-04-18.)

## [0.2.0] - 2026-04-18

First PyPI release of the core `yigthinker` package. Two MCP server packages
(`yigthinker-mcp-uipath`, `yigthinker-mcp-powerautomate`) publish as `0.1.0a1`
alpha name-reservations pending live-tenant UAT — do NOT depend on them for
production until a `0.2.0` release is cut after successful round-trip against
real Automation Cloud / Power Automate tenants.

Highlights of what landed since 0.1.0 was drafted but never published:

- **Teams channel: tenant-validated** against real Bot Framework + devtunnel on 2026-04-18 (see `docs/audit/2026-04-18-teams-uat-report.md` locally). 6 bugs caught and fixed in the same UAT session.
- **`excel_write` can now embed native openpyxl charts** via `embed_chart=<chart_name>` (bar / line / pie), closing the "give me an Excel with the chart embedded" UX gap.
- **post-v1.1 P1 arch gaps (all 6)** shipped inline with Phase 1b / quick tasks: streaming tool feedback, session branching + checkpoints, file undo, richer hook responses, sub-agent isolation, MCP resources.
- **Voice provider**: real OpenAI Whisper wiring + loud-failure semantics (no more silent empty-string on unconfigured API key).
- **Gateway**: per-session PermissionSystem overrides now cleaned up on session removal (hibernate / evict / shutdown / remove).
- **Scheduled reports**: durable file-backed registry at `~/.yigthinker/scheduled_reports.json`.
- **Open-source hygiene**: SECURITY.md + CONTRIBUTING.md added; PyPI metadata complete across all three packages; `twine check` passes clean.

See the sections below for the full granular change set. All items inherited from the pre-0.2.0 `[Unreleased]` draft are grouped under this release.

### Reports — durable scheduled reports (persistence layer, 2026-04-17)

- New `ScheduleRegistry` file-backed store at `~/.yigthinker/scheduled_reports.json`. Atomic writes via filelock + `os.replace` (same pattern as `WorkflowRegistry`). Versioned on-disk format.
- `ReportScheduleTool` constructor now accepts `registry: ScheduleRegistry | None = None`. With a registry, entries persist across restarts; without, tool runs session-only for backward compat.
- `registry_factory.build_tool_registry()` wires a default `ScheduleRegistry()` so production gets durability by default.
- Tool result now includes architect-not-executor `next_steps`: POSIX cron line, Windows Task Scheduler hint, and a pointer to `workflow_deploy` for richer hand-offs. The tool itself never executes schedules — no silent success.
- Dry-run path: no disk writes, no session-settings writes. Matches other file-producing tools.
- Follow-up tracked in TODOs.md: decide executor path (in-process APScheduler vs OS hand-off vs workflow_deploy integration).

### Gateway — permission override cleanup on session eviction (2026-04-17)

- `SessionRegistry` now exposes `add_session_removed_callback(cb)`; callbacks fire with `session.ctx.session_id` (UUID, not the registry key) when a session is removed via `hibernate` / `evict_idle` / `shutdown` / `_evict_lru` / `remove`.
- Errors from individual callbacks are logged and swallowed — no callback can block session lifecycle progression.
- `build_app()` now exposes `AppContext.permissions` so `GatewayServer.start()` can register `PermissionSystem.clear_session` as a callback automatically.
- Closes TODOs.md item: long-running gateways were previously leaking `PermissionSystem._session_overrides` entries across every hibernation.
- 7 regression tests in `tests/test_gateway/test_session_removal_callbacks.py`.

### Voice provider — loud failure + real OpenAI wiring (2026-04-17)

- `WhisperProvider` now wires the OpenAI `AsyncOpenAI.audio.transcriptions.create` endpoint (replacing the `NotImplementedError` stub)
- Raises new `VoiceNotConfiguredError` (subclass of `VoiceError`) when `OPENAI_API_KEY` is absent — with an actionable message naming the env var / kwarg
- API errors (network, rate limit, auth) propagate to the caller; silent-empty-string-on-error behavior removed
- Empty string is reserved for the one legitimate case: Whisper reports "no speech detected"
- API key resolved at construction from explicit `api_key=` kwarg or `OPENAI_API_KEY` env; both paths tested
- Net +5 tests, 8 total in `tests/test_voice/test_providers.py`

Rationale: TODOs.md item "Silent failure is worse than an explicit unsupported message." Now closed.

### Post-v1.1 — P1 Arch Gap Closure (shipped inline, retro-documented 2026-04-17)

All 6 active items from `docs/superpowers/specs/2026-04-14-p1-arch-gaps-design.md` shipped via Phase 1b + quick tasks 260414–260416. The spec was drafted 2026-04-14 but never merged as a standalone milestone — the work was executed inline.

- **P1-1 Streaming tool execution feedback**: `SessionContext._progress_callback` + `emit_progress()`; AgentLoop wires callback before each tool; delivery via `on_tool_event` → CLI/TUI/Teams/Feishu/GChat/SDK
- **P1-2 Session branching + checkpoints**: `checkpoint(label)` / `branch_from(label)` / `branch()` / `list_checkpoints()` on `SessionContext`; `CheckpointData` with deep-copied messages + DataFrame snapshots; max 10 per session (configurable)
- **P1-3 File undo**: `UndoEntry` dataclass + `session.undo_stack` (max 20, configurable); `snapshot_before_write` / `undo_file` / `cleanup_backups` helpers in `yigthinker/tools/_file_undo.py`; `/undo` command handler wired on Teams adapter. **Per-tool integration** (closed 2026-04-17 evening): `report_generate` snapshots once at the dispatch site covering all 5 formats (csv/excel/pdf/docx/pptx); `workflow_deploy` snapshots 3 local-mode artifacts (task_scheduler.xml, crontab.txt, setup_guide.md) + 1 guided-mode setup guide. Excluded by design: `chart_create` (no file writes, returns Plotly JSON), `report_template` (no writes), `workflow_generate` (registry-managed versioning IS the undo mechanism per ADR-006). Out of scope for this pass: bundle ZIP in guided/auto deploy.
- **P1-5 Richer hook responses** (breaking change to `HookExecutor.run()` return type): `HookAction.INJECT_SYSTEM` / `SUPPRESS_OUTPUT` / `REPLACE_RESULT`; `HookResult.inject_system(text)` / `.suppress()` / `.replace(content)` classmethods; aggregate return via `HookAggregateResult`; 2048-token injection cap; two-layer config (per-hook `enabled` + global `hooks.capabilities` toggles)
- **P1-6 Sub-agent session isolation**: `ctx._session_registry` wired in Gateway `handle_message`; `dataframes=["*"]` wildcard expansion; background merge-back looks up live session (skips safely if parent evicted); 3 regression tests in `tests/test_subagent/test_isolation_patches.py`
- **P1-7 MCP resources support**: `MCPClient.list_resources()` / `.read_resource(uri)`; conditional dynamic registration of `mcp_list_resources` + `mcp_read_resource` tools when any server exposes resources

**Deferred** (per spec): P1-4 Bedrock / Vertex providers (no customer demand yet), P1-8 Cost tracking (providers don't return token counts yet).

### Post-v1.1 — Phase 1b: Harness & Presence (2026-04-17, merge `8a831d9`)

**Added**
- `yigthinker/presence/` tree: `channels/` + `gateway/` + `cli/` + `tui/` (blame-preserving git-mv refactor)
- `yigthinker/core/presence.py`: `ChannelAdapter` Protocol with required `deliver_artifact` method
- `scripts/check_presence_boundaries.py`: AST-based import-graph lint (zero allowlisted violations)
- Agent harness: idle watchdog (`settings.agent.stream_idle_timeout_seconds`, default 30), dry-run mode (`ctx.dry_run`), arg-patch reflexion (`settings.agent.reflexion_enabled`, default false)
- MCP client patches: auto-reconnect-once, parallel server discovery, stable sort, constant-time equality helper
- `report_generate` pptx format (ported Yigcore engine)

### Post-v1.1 — Phase 1a: Harvest & Docs (2026-04-17, merge `2eca51e`)

**Added**
- 8 ADRs under `docs/adr/` (001–008): PGEC rationale, intent routing, harness philosophy, governance sidecar, MemoryProvider interface, workflow templating, plugin/skill distribution, persona-as-data
- `MemoryProvider` Protocol + `MemoryRecord` dataclass (`yigthinker/memory/provider.py`)
- `FileMemoryProvider`: stdlib+filelock JSONL store
- Dormant SQLAlchemy schemas: `ltm_schema.py` + `agent_profile.py`
- 25 persona cards + 3 team cards at `yigthinker/presets/`
- ADR format validator at `scripts/check_adr_format.py`

### Post-v1.1 — Phase 0: P0 Arch Gap Closure (2026-04-17)

**Added**
- P0-1 Extended Thinking: `ThinkingConfig` in `yigthinker/types.py`; thinking blocks preserved in AgentLoop message history; `settings.thinking` key
- P0-2 MCP multi-transport: `MCPClient` supports `stdio` / `sse` / `http`; loader routes by `transport` field in `.mcp.json`
- P0-3 Plugin system enrichment: `CommandHook` subprocess wrapper; `PluginManifest.hooks_config`; builder wires plugin hooks + MCP
- P0-4 Agent SDK: public `yigthinker.sdk` module exposing `query()`, `create_session()`, `resume_session()`
- P0-5 Permission modes: `PermissionMode = Literal["default", "acceptEdits", "bypassAll", "denyAll"]`

### LangAlpha-inspired improvements (2026-04-14 → 2026-04-16, 21 tasks across P0/P1/P2/P3)

**Added**
- Leak detection PostToolUse hook (`yigthinker/hooks/leak_detection.py`)
- `yigthinker/visualization/` package: `ChartExporter` (Plotly → PNG via kaleido, HTML), `vchart.py` (Plotly → VChart translation for Feishu)
- Live steering: `SessionContext._steering_queue` + `ctx.steer(...)` + agent drains at each turn; Gateway routes follow-ups into queue
- Gateway `/api/charts/{chart_id}.png` signed-URL endpoint (7-day TTL sweep)
- Teams chart image card + native table card + Action.OpenUrl binary artifact delivery
- Feishu VChart native card + native table card
- Quote/reference extraction: `extract_quoted_messages` on ChannelAdapter Protocol; Teams + Feishu implementations; gateway `_prepend_quoted_context`
- `/ref` multi-quote slash command
- `df_transform` `extra_vars` for multi-DataFrame merges (with protected-namespace-key guard)
- `df_transform` wall-clock timeout (default 30s, settings-overridable)
- VarRegistry 2 GB default memory limit
- Waterfall chart type in `chart_create`
- DOCX report format in `report_generate` (via python-docx)
- PDF pagination fix via reportlab `LongTable`
- `artifact_write` tool + `excel_write` tool (named styles, base-file modify mode)
- Hook injection sanitization (strips prompt-injection patterns from hook-injected content and steerings)

**Fixed**
- `df_transform` getattr sandbox escape (dunder/concatenation blocked)
- Checkpoint shallow-copy corruption (now deep-copies DataFrames)
- Heatmap crash in `chart_create`

### v1.1 Workflow & RPA Bridge (shipped 2026-04-12)

**Added** — Phases 8–12, 26 plans, ~31,785 LOC, 67 commits (see `.planning/milestones/v1.1-MILESTONE-AUDIT.md` for full detail):
- `workflow_generate` / `workflow_deploy` / `workflow_manage` / `suggest_automation` tools
- WorkflowRegistry with filelock + atomic `os.replace` + sequential versioning
- Jinja2 `SandboxedEnvironment` templates + AST validation (two-layer SSTI prevention)
- 3 deploy modes × 3 targets: local OS scheduler, guided paste-ready, auto API
- Gateway `/api/rpa/callback` (Bearer auth, sqlite3 dedup, circuit breaker 3/24h + 10/day)
- Extraction-only LLM path for RPA self-healing; PatternStore for cross-session automation detection
- Independent `packages/yigthinker-mcp-uipath`: OAuth2 + OrchestratorClient (10 OData wrappers, 3-retry backoff) + `build_nupkg` + 5 MCP tool handlers
- Independent `packages/yigthinker-mcp-powerautomate`: MSAL ConfidentialClientApplication + PowerAutomateClient (7 domain methods) + flow_builder + 5 MCP tool handlers
- "Automate everything" system prompt directive; startup health alerts

### Added (pre-v1.1, consolidated from earlier drafts)
- 4 finance tools: `finance_calculate`, `finance_analyze`, `finance_validate`, `finance_budget`
- IRR convergence check (returns error instead of wrong answer on non-convergent cash flows)
- Depreciation period validation (rejects period < 1)
- Scenario probability validation (rejects partial or mis-summed probabilities)
- `plotly` and `httpx` added to core dependencies (no longer crash on bare install)
- Quickstart now registers sample database as a named connection
- LICENSE file (MIT)
- CHANGELOG.md

### Removed
- Dashboard module and all dashboard-related commands (headless product by design)
- `dashboard_push` tool (replaced by finance tools)
- Dashboard entries cap at 500 in gateway (legacy stub endpoints retained for API compat only)

### Fixed
- GitHub URLs corrected from `gaoyu` to `Henghenggao` in installer scripts
- README rewritten to reflect current headless architecture

## [0.1.0] - 2026-04-07

### Added
- Agent loop with flat tool registry (26 tools)
- 4 LLM providers: Claude, OpenAI, Ollama, Azure
- SQL tools: `sql_query`, `sql_explain`, `schema_inspect`
- DataFrame tools: `df_load`, `df_transform`, `df_profile`, `df_merge`
- Visualization tools: `chart_create`, `chart_modify`, `chart_recommend`
- Report tools: `report_generate`, `report_template`, `report_schedule`
- Exploration tools: `explore_overview`, `explore_drilldown`, `explore_anomaly`
- Forecast tools (optional): `forecast_timeseries`, `forecast_regression`, `forecast_evaluate`
- Sub-agent tools: `spawn_agent`, `agent_status`, `agent_cancel`
- FastAPI gateway with WebSocket protocol and session management
- Textual TUI client
- Channel adapters: Feishu, Teams, Google Chat
- Hook system with PreToolUse/PostToolUse events
- Permission system (allow/ask/deny rules)
- Session persistence (JSONL transcripts) and hibernation (Parquet)
- Session memory with auto-dream consolidation
- MCP integration for external tool loading
- Plugin system with slash commands
- One-line installer for macOS/Linux/Windows
