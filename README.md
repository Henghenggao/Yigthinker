# Yigthinker

Yigthinker is a headless AI agent for financial and data analysis. It runs as a CLI REPL, a FastAPI gateway daemon, a Textual TUI, or behind messaging channel webhooks (Feishu, Teams, Google Chat) — same agent, multiple surfaces, no web dashboard.

It combines:

- An LLM-driven agent loop with 32 registered tools (28 core + 4 workflow optional), 3 more with the `forecast` extra
- Session-scoped in-memory DataFrame storage (`ctx.vars`)
- A hook system for permissions, auditing, and cross-cutting concerns
- 4 LLM providers: Claude, OpenAI, Ollama, Azure

## Quick Start

### 1. Install

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Henghenggao/Yigthinker/master/install.sh | bash

# Windows (PowerShell)
irm https://raw.githubusercontent.com/Henghenggao/Yigthinker/master/install.ps1 | iex
```

The installer sets up [uv](https://docs.astral.sh/uv/) and walks you through component selection.
Until PyPI publication lands, it runs Yigthinker directly from this GitHub repo and installs the selected extras from the same source.

### 2. First run

```bash
yigthinker quickstart
```

This does three things:
1. Configures your LLM provider and API key
2. Creates a sample finance database (revenue, accounts payable, expenses)
3. Starts the gateway on `http://127.0.0.1:8766`

Once the gateway is running, open a second terminal:

```bash
yigthinker tui
```

### 3. Try a query

In the REPL or TUI, type:

```text
Show total revenue by region for 2025 from the sample database
```

The agent will use `sql_query` on the sample database, then render a summary.

## Manual Installation

Current manual installs also use the GitHub source directly:

```bash
# Core (CLI + all tools)
uv tool install "yigthinker @ git+https://github.com/Henghenggao/Yigthinker.git"

# With gateway + TUI
uv tool install "yigthinker[gateway,tui] @ git+https://github.com/Henghenggao/Yigthinker.git"

# With workflow automation compatibility extra
uv tool install "yigthinker[workflow] @ git+https://github.com/Henghenggao/Yigthinker.git"

# With forecasting (statsmodels, scikit-learn, prophet)
uv tool install "yigthinker[forecast] @ git+https://github.com/Henghenggao/Yigthinker.git"

# Everything including channel adapters and RPA bridges
uv tool install "yigthinker[gateway,tui,forecast,workflow,feishu,teams,gchat,rpa-uipath,rpa-pa] @ git+https://github.com/Henghenggao/Yigthinker.git"
```

### Extras Reference

| Extra | What it adds |
|-------|-------------|
| `forecast` | statsmodels, scikit-learn, prophet |
| `gateway` | FastAPI, uvicorn, websockets, pyarrow |
| `tui` | Textual, websockets |
| `workflow` | Backwards-compat alias; workflow deps are in the core install |
| `feishu` | Lark/Feishu SDK |
| `teams` | httpx, msal (Azure AD) |
| `gchat` | Google API client, google-auth |
| `rpa-uipath` | yigthinker-mcp-uipath package |
| `rpa-pa` | yigthinker-mcp-powerautomate package |

### For Contributors

```bash
git clone https://github.com/Henghenggao/Yigthinker.git
cd Yigthinker
python scripts/run_all_tests.py
```

## CLI Commands

```bash
yigthinker                      # Start interactive REPL
yigthinker "your query here"    # Single-shot query
yigthinker --resume             # Resume last session
yigthinker setup                # Configure provider + API key only
yigthinker quickstart           # First-time guided setup
yigthinker install              # Interactive component installer
yigthinker gateway              # Start gateway daemon (foreground)
yigthinker tui                  # Launch TUI (connects to gateway)
```

## Configuration

Create `.yigthinker/settings.json` (project) or `~/.yigthinker/settings.json` (user):

```json
{
  "model": "claude-sonnet-4-20250514",
  "permissions": {
    "allow": ["schema_inspect", "df_profile", "chart_recommend"],
    "ask": ["sql_query", "df_transform", "report_generate"],
    "deny": ["sql_query(DELETE:*)", "sql_query(DROP:*)"]
  },
  "connections": {
    "finance": {
      "type": "sqlite",
      "database": "./finance.db"
    }
  }
}
```

API keys can be set as environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`) or saved in user settings during `yigthinker quickstart`.

Ollama requires no API key — it uses the local HTTP endpoint at `http://localhost:11434`.

## Tool Surface

### Always available (28 tools)

| Category | Tools |
|----------|-------|
| SQL | `sql_query`, `sql_explain`, `schema_inspect` |
| DataFrame | `df_load`, `df_transform`, `df_profile`, `df_merge` |
| Visualization | `chart_create`, `chart_modify`, `chart_recommend` |
| Reports | `report_generate`, `report_template`, `report_schedule` |
| File output | `artifact_write`, `excel_write` |
| Exploration | `explore_overview`, `explore_drilldown`, `explore_anomaly` |
| Finance | `finance_calculate`, `finance_analyze`, `finance_validate`, `finance_budget` |
| Agent | `spawn_agent`, `agent_status`, `agent_cancel` |

### Optional (require `forecast` extra — 3 tools)

`forecast_timeseries`, `forecast_regression`, `forecast_evaluate`

### Optional (require `workflow` extra + Jinja2 — 4 tools)

`workflow_generate`, `workflow_deploy`, `workflow_manage`, `suggest_automation`

**Total:** 28 core + 3 forecast + 4 workflow = up to **32 tools** with all extras.

## Built-in Slash Commands

```
/help                   Show available commands
/vars                   List in-memory DataFrames
/connect <name>         Switch database connection
/schema [table]         Inspect database schema
/history                Show conversation history
/export                 Export session data
/schedule               Manage report schedules
/stats                  Show session statistics
/advisor [off|model]    Toggle dual-model advisor
/voice [on|off|lang]    Toggle voice input
```

Plugin-provided commands are loaded from `~/.yigthinker/plugins` and `.yigthinker/plugins`.

## Architecture

```
User input
  |
  v
Entry point (CLI / Gateway WS / Channel webhook)
  |
  v
AgentLoop.run(user_input, session_context)
  |
  +---> LLM call (Claude / OpenAI / Ollama / Azure)
  |       |
  |       v
  |     Parse response: text | tool_use | end_turn
  |       |
  |     tool_use:
  |       +---> PreToolUse hooks (permissions, audit)
  |       +---> tool.execute(input, ctx)
  |       +---> PostToolUse hooks
  |       +---> tool_result -> loop back to LLM
  |
  v
end_turn -> output to user
```

Key directories:

| Path | Purpose |
|------|---------|
| `yigthinker/agent.py` | Agent loop |
| `yigthinker/session.py` | Session context + VarRegistry |
| `yigthinker/providers/` | LLM provider implementations |
| `yigthinker/tools/` | All 32 tool implementations (28 core + 3 forecast + 4 workflow) |
| `yigthinker/presence/gateway/` | Gateway server, session registry, protocol |
| `yigthinker/presence/tui/` | Textual TUI client |
| `yigthinker/presence/channels/` | Feishu, Teams, Google Chat adapters |
| `yigthinker/core/` | Stable shared kernel (ChannelAdapter Protocol, build_app re-export) |
| `yigthinker/hooks/` | Hook registry and executor |
| `yigthinker/memory/` | Session memory and auto-dream |
| `yigthinker/mcp/` | MCP integration |

## Gateway + Channels

The gateway is a long-running FastAPI daemon that manages multiple sessions:

```bash
yigthinker gateway --host 127.0.0.1 --port 8766
```

It exposes:
- `/ws` — WebSocket for TUI and API clients
- `/api/sessions` — Session management REST API
- `/health` — Liveness check
- Webhook routes registered by channel adapters

### Channel adapters

Configure in `.yigthinker/settings.json`:

```json
{
  "channels": {
    "feishu": { "enabled": true, "app_id": "...", "app_secret": "..." },
    "teams": {
      "enabled": true,
      "tenant_id": "...",
      "client_id": "...",
      "client_secret": "...",
      "webhook_secret": "..."
    },
    "gchat": { "enabled": true, "service_account_file": "..." }
  }
}
```

Channel adapters handle platform-specific auth (Feishu token verification, Teams Bot Framework bearer auth or legacy HMAC, Google service accounts) and route messages through the same `AgentLoop.run()` as CLI and TUI. For standard Teams bot manifests, `tenant_id` / `client_id` / `client_secret` are required; `webhook_secret` is only for legacy Outgoing Webhook mode.

## Testing

```bash
python scripts/run_all_tests.py                 # Install test deps + run all suites
python scripts/run_all_tests.py --skip-install  # Reuse current environment
python -m pytest tests/test_gateway/ -q         # Gateway tests only
python -m pytest tests/test_tools/ -q           # Tool tests only
```

Current workspace status:

- Core repo: **1179 passed, 1 skipped, 1 deselected**
- `yigthinker-mcp-uipath`: **47 passed**
- `yigthinker-mcp-powerautomate`: **52 passed**

## Limitations

- **PyPI publication is still pending.** The one-line installer and manual `uv tool install` examples currently install from the GitHub repo source.
- The gateway runs in the foreground; no built-in daemon manager (use systemd, supervisor, or similar).
- `report_schedule` persists entries durably to `~/.yigthinker/scheduled_reports.json` and returns cron / Task Scheduler hand-off instructions, but does not run schedules in-process. Execution path (APScheduler vs OS hand-off vs workflow_deploy integration) is deferred — see `docs/adr/009-scheduled-reports-executor.md`.
- Forecast tools only register when their scientific dependencies are installed.
- Channel adapters: Teams is integration-validated; Feishu and Google Chat adapters ship code-complete but have not been formally round-tripped against a live tenant.
- MCP server packages (`yigthinker-mcp-uipath`, `yigthinker-mcp-powerautomate`) are code-complete against API specs but have not been validated against live Automation Cloud / Power Automate tenants — treat as beta until a round-trip UAT is recorded.
- `spawn_agent` background mode merges DataFrames back only for sessions that are still alive at completion; parent eviction skips the merge with a warning (by design).
- SQL queries pass LLM-generated SQL directly; use read-only database users for safety.

## License

[MIT](LICENSE)
