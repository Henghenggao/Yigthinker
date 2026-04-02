# Yigthinker

**AI-powered financial and data analysis agent for enterprise teams.**

Query your databases in plain language, generate charts and reports, run forecasts, detect anomalies — all from a CLI or web dashboard.

```bash
yigthinker "分析应收账款账龄并生成Excel报告"
# → queries DB → classifies aging → forecasts collection → charts + Excel report
```

## Features

- **Natural language SQL** — query PostgreSQL, MySQL, Snowflake, and more in plain English or Chinese
- **DataFrame analysis** — load, transform, merge, and profile data with Pandas/Polars
- **Interactive charts** — Plotly visualizations in CLI (ASCII) or Web Dashboard
- **Financial reports** — Excel/PDF/Word from templates (balance sheet, income statement, cash flow)
- **Forecasting** — time series (Prophet/statsmodels) and multi-factor regression
- **Anomaly detection** — statistical outlier detection with root cause dimension analysis
- **Multi-model** — Claude, GPT-4, Ollama (local), Azure OpenAI
- **MCP connectors** — connect SAP, Yonyou, Kingdee, Bloomberg, Wind via the [Model Context Protocol](https://modelcontextprotocol.io)
- **Enterprise** — RBAC, audit logging, data masking, approval workflows, SSO (commercial)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI (Typer/Rich)  │  Web Dashboard (FastAPI + Plotly Dash)     │
├─────────────────────────────────────────────────────────────────┤
│  Agent Loop — tool_use cycle │ LLM Provider │ Context Manager   │
├─────────────────────────────────────────────────────────────────┤
│  Tool Registry (21 tools, flat)                                  │
│  sql_query · df_transform · chart_create · report_generate · …  │
├─────────────────────────────────────────────────────────────────┤
│  Hook System (PreToolUse / PostToolUse / Stop / SessionStart)    │
│  MCP Servers (ERP connectors, market data, internal APIs)        │
│  Plugins (commands/*.md · hooks/ · .mcp.json)                   │
├─────────────────────────────────────────────────────────────────┤
│  Settings (.yigthinker/settings.json)                           │
│  managed > user > project · allow/ask/deny permissions          │
└─────────────────────────────────────────────────────────────────┘
```

The core design principle is **tools over abstractions**: every capability is a flat, independently testable tool registered directly in the agent loop. Cross-cutting concerns (permissions, audit, masking) live in the hook system — not baked into tools or the loop itself.

The one domain-specific addition: a **DataFrame Variable Registry** in `SessionContext` keeps in-memory DataFrames alive across tool calls within a session, since DataFrames — unlike files — don't persist naturally.

## Installation

```bash
pip install yigthinker
```

**Requirements:** Python 3.11+

**Optional dependencies:**

```bash
pip install yigthinker[forecast]    # Prophet, statsmodels, scikit-learn
pip install yigthinker[dashboard]   # FastAPI, Plotly Dash
pip install yigthinker[voice]       # sounddevice, openai (Whisper)
pip install yigthinker[enterprise]  # Commercial features (requires license)
```

## Quick Start

```bash
# Interactive REPL
yigthinker

# Single query
yigthinker "show me revenue by region for Q1"

# Connect to a database
yigthinker connect production_db

# View connected schema
yigthinker schema

# Launch web dashboard
yigthinker dashboard

# Resume last session
yigthinker --resume
```

## Configuration

Create `.yigthinker/settings.json` in your project root:

```json
{
  "model": "claude-sonnet-4-20250514",
  "fallback_model": "gpt-4o",

  "connections": {
    "production_db": {
      "type": "postgresql",
      "host": "db.company.com",
      "database": "finance",
      "credentials": "vault://finance/readonly",
      "read_only": true,
      "max_rows": 100000,
      "timeout_seconds": 30
    },
    "local_data": {
      "type": "file",
      "path": "./data/",
      "watch": true
    }
  },

  "permissions": {
    "allow": ["schema_inspect", "chart_create", "chart_recommend", "df_profile"],
    "ask": ["sql_query", "df_transform", "report_generate", "forecast_timeseries"],
    "deny": ["sql_query(DELETE:*)", "sql_query(DROP:*)", "sql_query(UPDATE:*)"]
  },

  "theme": {
    "palette": ["#1e40af", "#3b82f6", "#93c5fd", "#dbeafe"],
    "number_format": "¥#,##0",
    "date_format": "%Y-%m-%d"
  }
}
```

User-level defaults go in `~/.yigthinker/settings.json`.

## Tools Reference

| Category | Tool | Description |
|----------|------|-------------|
| SQL | `sql_query` | Execute SQL against configured connections |
| SQL | `sql_explain` | Show query execution plan |
| SQL | `schema_inspect` | View table structure and sample data |
| DataFrame | `df_load` | Load CSV/Excel/Parquet/JSON/DB into named DataFrame |
| DataFrame | `df_transform` | Run Pandas/Polars code in sandboxed namespace |
| DataFrame | `df_profile` | Data quality: missing values, distributions, outliers |
| DataFrame | `df_merge` | Join two DataFrames with auto key inference |
| Charts | `chart_create` | Generate Plotly chart from DataFrame or query |
| Charts | `chart_modify` | Modify chart style via natural language |
| Charts | `chart_recommend` | Recommend chart types for a dataset |
| Charts | `dashboard_push` | Push chart/table/KPI to Web Dashboard |
| Reports | `report_generate` | Generate Excel/PDF/Word from template + data |
| Reports | `report_template` | List and manage report templates |
| Reports | `report_schedule` | Schedule recurring report generation |
| Forecast | `forecast_timeseries` | Time series forecasting with confidence intervals |
| Forecast | `forecast_regression` | Multi-factor regression analysis |
| Forecast | `forecast_evaluate` | Evaluate forecast accuracy (MAPE, RMSE, R²) |
| Explore | `explore_overview` | Dataset overview: metrics, distributions, data quality |
| Explore | `explore_drilldown` | Drill down by dimension with auto-chart |
| Explore | `explore_anomaly` | Detect anomalies + suggest root cause dimensions |
| Agent | `spawn_agent` | Spawn a subagent with isolated DataFrame snapshot |

## Slash Commands

| Command | Description |
|---------|-------------|
| `/connect <name>` | Switch active data connection |
| `/vars` | Inspect DataFrame variable registry |
| `/schema` | View current connection schema |
| `/stats` | Show session usage statistics |
| `/history` | View session history |
| `/advisor [off\|model]` | Configure financial advisor review |
| `/voice [on\|off\|lang]` | Toggle voice input mode |

Add custom commands by placing `.md` files in `commands/`.

## MCP Connectors

External systems connect via the [Model Context Protocol](https://modelcontextprotocol.io) (`.mcp.json`):

```json
{
  "mcpServers": {
    "sap": {
      "command": "yigthinker-mcp-sap",
      "args": ["--client", "800", "--host", "sap.company.com"],
      "env": { "SAP_USER": "vault://sap/user", "SAP_PASS": "vault://sap/pass" }
    },
    "wind": {
      "command": "yigthinker-mcp-wind",
      "args": ["--api-key-env", "WIND_API_KEY"]
    }
  }
}
```

Available MCP packages: `yigthinker-mcp-sap`, `yigthinker-mcp-yonyou`, `yigthinker-mcp-kingdee`, `yigthinker-mcp-wind`, `yigthinker-mcp-bloomberg` (commercial)

## Hooks

Extend behavior without modifying core code:

```python
from yigthinker.hooks import hook, HookEvent, HookResult

@hook("PreToolUse", matcher="sql_query")
async def check_field_permissions(event: HookEvent) -> HookResult:
    if contains_sensitive_fields(event.tool_input, event.session.user):
        return HookResult.BLOCK("Access denied: salary field requires Admin role")
    return HookResult.ALLOW

@hook("PostToolUse", matcher="*")
async def audit_log(event: HookEvent) -> HookResult:
    write_audit_entry(event)
    return HookResult.ALLOW
```

Command hooks (shell scripts) use exit codes: `0` = allow, `1` = warn, `2` = block.

Hook events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`, `PreCompact`

## Plugins

```
yigthinker-plugin-name/
  .yigthinker-plugin/plugin.json
  commands/*.md          # slash commands
  hooks/hooks.json       # hook definitions
  .mcp.json              # MCP server definitions
  templates/             # report templates
```

## Enterprise Features

The `yigthinker-enterprise` plugin (commercial subscription) adds:

- **RBAC** — field-level permissions via PreToolUse hooks + managed settings
- **Audit logging** — structured log: who, what, when, full tool trace
- **Data masking** — sensitive fields masked before the LLM sees them; output masked by role
- **Approval workflows** — operations matching approval rules block → notify approver (DingTalk/Feishu/Slack) → re-submit on approval
- **SSO** — LDAP, OAuth2, SAML via SessionStart hook
- **ERP connectors** — SAP, Yonyou, Kingdee, Oracle EBS MCP servers
- **Team collaboration** — shared sessions, report sharing
- **Scheduled tasks** — APScheduler-based report and analysis scheduling

## Technology Stack

| Layer | Technology |
|-------|-----------|
| CLI | Python 3.11+, Typer, Rich |
| Web Dashboard | FastAPI, Plotly Dash, WebSocket |
| Data Processing | Pandas, Polars, NumPy |
| SQL | SQLAlchemy, asyncpg, aiomysql |
| Visualization | Plotly |
| Reports | openpyxl, reportlab, python-docx, Jinja2 |
| Forecasting | Prophet, statsmodels, scikit-learn |
| LLM | anthropic SDK, openai SDK, ollama |

## License

MIT License — see [LICENSE](LICENSE)

Enterprise plugin: commercial subscription
