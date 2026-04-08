# Yigthinker

Yigthinker is a Python agent for data analysis workflows across CLI, Gateway, TUI, dashboard, and messaging channels.

It combines:

- an LLM-driven agent loop with tool calling
- session-scoped DataFrame storage
- a FastAPI Gateway for multi-session access
- a Textual TUI client
- optional dashboard, forecasting, and channel integrations

The current `master` branch has completed the v1 stabilization milestone and the full local test suite is green.

## What It Can Do

- Query configured databases with `sql_query`, `sql_explain`, and `schema_inspect`
- Load, transform, merge, and profile DataFrames in-session
- Create and modify charts, and push entries to the dashboard queue
- Run exploration helpers for overview, drilldown, and anomaly detection
- Start a Gateway and connect a TUI client over WebSocket
- Stream token output through the Gateway/TUI path
- Persist session state and hibernate idle Gateway sessions
- Accumulate session memory and run background "auto dream" consolidation
- Expose experimental adapters for Teams, Feishu, and Google Chat

## Honest Status Notes

- `spawn_agent` is registered but intentionally returns a "not implemented" error.
- `report_schedule` stores schedules in session memory only; it is not a persistent scheduler.
- Forecast tools are optional and only register when their scientific dependencies are installed.
- Channel adapters are present, but should still be treated as integration-level features rather than polished product surfaces.

## Installation

One command to install:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/gaoyu/Yigthinker/master/install.sh | bash

# Windows (PowerShell)
irm https://raw.githubusercontent.com/gaoyu/Yigthinker/master/install.ps1 | iex
```

The installer will guide you through choosing components. After installation, run:

```bash
yigthinker setup    # Configure API keys and data sources
yigthinker          # Start the interactive REPL
```

### Manual Installation

If you prefer to install manually or the one-liner doesn't work in your environment:

```bash
# 1. Install uv (Python toolchain)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 2. Install yigthinker with your preferred extras
uv tool install "yigthinker[forecast,dashboard]"           # local analysis
uv tool install "yigthinker[forecast,dashboard,gateway,tui]"  # team server
uv tool install "yigthinker[forecast,dashboard,gateway,tui,feishu,teams,gchat]"  # everything
```

### Extras Reference

| Extra | What it adds |
|-------|-------------|
| `forecast` | statsmodels / scikit-learn / prophet |
| `dashboard` | FastAPI / Plotly / Uvicorn |
| `gateway` | FastAPI / websockets / pyarrow / Uvicorn |
| `tui` | Textual / websockets |
| `feishu` | Feishu / Lark SDK |
| `teams` | httpx / msal |
| `gchat` | Google API client / google-auth |

### For Contributors

```bash
git clone https://github.com/gaoyu/Yigthinker.git
cd Yigthinker
pip install -e ".[test]"
```

## Entry Points

The current Typer app exposes these top-level commands:

```bash
yigthinker
yigthinker "show me revenue by region for Q1"
yigthinker --resume
yigthinker dashboard
yigthinker gateway
yigthinker tui
```

Notes:

- `yigthinker` without arguments starts the interactive REPL.
- `yigthinker gateway` runs in the foreground and creates `~/.yigthinker/gateway.token` on first start.
- `yigthinker tui` expects that gateway token file to exist, so start the Gateway first.

## Quick Start

### 1. Configure a model

Create either:

- project settings at `.yigthinker/settings.json`
- user settings at `~/.yigthinker/settings.json`

Minimal example:

```json
{
  "model": "claude-sonnet-4-20250514",
  "permissions": {
    "allow": ["schema_inspect", "df_profile", "chart_recommend"],
    "ask": ["sql_query", "df_transform", "report_generate"],
    "deny": ["sql_query(DELETE:*)", "sql_query(DROP:*)", "sql_query(UPDATE:*)"]
  },
  "connections": {
    "finance": {
      "type": "sqlite",
      "database": "./finance.db"
    }
  }
}
```

Saved API keys in user settings are promoted into environment variables at load time:

- `anthropic_api_key` -> `ANTHROPIC_API_KEY`
- `openai_api_key` -> `OPENAI_API_KEY`
- `azure_openai_api_key` -> `AZURE_OPENAI_API_KEY`

### 2. Run the CLI

```bash
yigthinker
```

Example prompt:

```text
Load ./data/revenue.csv, profile it, and show anomalies by month.
```

### 3. Run Gateway + TUI

Terminal 1:

```bash
yigthinker gateway
```

Terminal 2:

```bash
yigthinker tui
```

### 4. Run the dashboard

```bash
yigthinker dashboard
```

Default URLs:

- dashboard: `http://127.0.0.1:8766/dashboard/`
- gateway health: `http://127.0.0.1:8766/health`

## Built-in Slash Commands

The CLI command router currently supports:

- `/help`
- `/vars`
- `/connect <name>`
- `/schema [table]`
- `/history`
- `/export`
- `/schedule`
- `/stats`
- `/advisor [off|model]`
- `/voice [on|off|lang <code>]`

Plugin-provided slash commands are loaded from:

- `~/.yigthinker/plugins`
- `.yigthinker/plugins` in the current project

## Tool Surface

Always available:

- SQL: `sql_query`, `sql_explain`, `schema_inspect`
- DataFrame: `df_load`, `df_transform`, `df_profile`, `df_merge`
- Charts: `chart_create`, `chart_modify`, `chart_recommend`, `dashboard_push`
- Reports: `report_generate`, `report_template`, `report_schedule`
- Exploration: `explore_overview`, `explore_drilldown`, `explore_anomaly`
- Agent: `spawn_agent`

Registered only when forecast dependencies are installed:

- `forecast_timeseries`
- `forecast_regression`
- `forecast_evaluate`

## Architecture

Core flow:

1. `build_app()` wires provider, tools, hooks, permissions, and DB pool.
2. `AgentLoop` runs the message -> tool_use -> tool_result cycle.
3. `SessionContext` stores messages, stats, context manager state, and DataFrame variables.
4. `GatewayServer` manages session keys, WebSocket clients, and session hibernation.
5. `YigthinkerTUI` connects to the Gateway and renders chat, vars, tool cards, and streamed output.

Important directories:

- `yigthinker/agent.py` - agent loop
- `yigthinker/builder.py` - app construction
- `yigthinker/gateway/` - Gateway, session registry, protocol, hibernation
- `yigthinker/tui/` - Textual client
- `yigthinker/tools/` - tool implementations
- `yigthinker/memory/` - session memory, compaction, auto dream
- `yigthinker/channels/` - Teams / Feishu / Google Chat adapters
- `tests/` - full automated test suite

## Testing

Run the full suite:

```bash
python -m pytest -q
```

Current local status on this branch:

```text
359 passed
```

Examples:

```bash
python -m pytest tests/test_gateway/test_session_registry.py -q
python -m pytest tests/test_tui -q
python -m pytest tests/test_memory/test_auto_dream.py -q
```

Forecast tests use `pytest.importorskip` for missing scientific packages, but the main dashboard, gateway, and TUI suites assume the matching runtime dependencies are installed. Using `.[test]` is the simplest contributor setup.

## Channels

The Gateway can mount optional webhook adapters from settings:

- `channels.teams`
- `channels.feishu`
- `channels.gchat`

The Teams adapter currently:

- verifies webhook HMAC signatures
- derives a session key from sender identity
- sends Adaptive Card responses using `httpx` + `msal`

## Limitations

- No daemon manager is included; the Gateway runs in the foreground.
- `spawn_agent` is a placeholder tool today.
- Scheduled reports are not persisted across restarts.
- README examples are intentionally aligned to the current codebase, not a future product surface.

## License

MIT
