# Changelog

All notable changes to Yigthinker are documented in this file.

## [Unreleased]

### Added
- 4 finance tools: `finance_calculate`, `finance_analyze`, `finance_validate`, `finance_budget`
- IRR convergence check (returns error instead of wrong answer on non-convergent cash flows)
- Depreciation period validation (rejects period < 1)
- Scenario probability validation (rejects partial or mis-summed probabilities)
- Dashboard entries capped at 500 in gateway (prevents unbounded memory growth)
- `plotly` and `httpx` added to core dependencies (no longer crash on bare install)
- Quickstart now registers sample database as a named connection
- LICENSE file (MIT)
- CHANGELOG.md

### Removed
- Dashboard module and all dashboard-related commands
- `dashboard_push` tool (replaced by finance tools)

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
