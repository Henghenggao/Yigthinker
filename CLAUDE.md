# Yigthinker — Developer Context

## What This Is

Yigthinker is a Python-based AI agent for financial and data analysis. It uses a flat tool registry, a single agent loop, a hook system for cross-cutting concerns, a permission system, MCP integration for external systems, and a plugin system — all adapted for in-memory DataFrame operations on financial data.

Design spec: `docs/superpowers/specs/2026-04-01-yigthinker-design.md`

## Architecture Principles

- **Flat tools** — all 21 tools registered directly in the Agent Loop; no grouping or agent personas at runtime
- **Tool Registration** — `(name, input_schema, handler)` tuple; Pydantic model → auto JSON Schema; no `risk_level` or `validate()` on tools
- **Permissions are external** — settings.json `allow/ask/deny` + pattern matching; PreToolUse Hooks handle validation
- **Hooks over hardcoded logic** — enterprise features (RBAC, audit, masking, approvals) are Hook implementations, not architectural layers
- **Slash commands are Markdown files** — `commands/*.md` with YAML frontmatter

## The One Deliberate Deviation from Standard Agent Patterns

**DataFrame Variable Registry** — Most agent tools operate on persistent storage (files, databases) that survives between tool calls naturally. Yigthinker tools operate on in-memory DataFrames that would be lost between tool calls without explicit session-scoped storage. Solution: `ctx.vars` registry.

```python
ctx.vars.set("df1", dataframe)   # register
ctx.vars.get("df1")              # retrieve
ctx.vars.list()                  # list all: [(name, shape, dtypes), ...]
```

This lives in `SessionContext`, NOT in the LLM message history.

## Tool Implementation Pattern

```python
class YigthinkerTool(Protocol):
    name: str                       # "sql_query"
    description: str                # LLM-facing description
    input_schema: type[BaseModel]   # Pydantic → JSON Schema
    async def execute(self, input: BaseModel, ctx: SessionContext) -> ToolResult
```

All tools: `sql_query`, `sql_explain`, `schema_inspect`, `df_load`, `df_transform`, `df_profile`, `df_merge`, `chart_create`, `chart_modify`, `chart_recommend`, `dashboard_push`, `report_generate`, `report_template`, `report_schedule`, `forecast_timeseries`, `forecast_regression`, `forecast_evaluate`, `explore_overview`, `explore_drilldown`, `explore_anomaly`, `spawn_agent`

## Hook Pattern

```python
@hook("PreToolUse", matcher="sql_query|df_transform")
async def my_hook(event: HookEvent) -> HookResult:
    return HookResult.ALLOW  # or .BLOCK("reason") or .WARN("message")
```

Command hooks use exit codes: 0 = allow, 1 = warn user only, 2 = block (stderr → LLM feedback).

Hook events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`, `PreCompact`

## Configuration

- Project: `.yigthinker/settings.json`
- User: `~/.yigthinker/settings.json`
- Managed (enterprise): highest priority, can lock below
- MCP servers: `.mcp.json` (standard Model Context Protocol format)

## Agent Loop Execution Order

1. User input → Context Builder (inject schemas, permissions, history)
2. LLM call with all registered tools
3. Parse: text / tool_use / end_turn
4. If tool_use: PreToolUse hooks → permission check → execute → PostToolUse hooks → build tool_result
5. If hook blocks (exit 2): stderr → LLM as feedback for replanning
6. Append tool_result → loop to step 2
7. end_turn → CLI output + WebSocket push to Dashboard

## Context Manager

Token budget: system 20% | data context (schemas + samples) 30% | history 40% | reserve 10%

Large result sets (100K+ rows): summarize in tool_result (schema + 10 rows + stats); full data stays internal, not in message history.

## Planner

Off by default. Enable via `settings.json` `planner.enabled: true`. Only for weak-planning models (e.g., small Ollama models). `exit_plan_mode` tool always available for the LLM to present a plan before dangerous operations.

## LLM Provider

```python
class LLMProvider(Protocol):
    async def chat(messages: list, tools: list, system: str | None = None) -> Response
    async def stream(messages: list, tools: list) -> AsyncIterator[StreamEvent]
```

Implementations: `ClaudeProvider`, `OpenAIProvider`, `OllamaProvider`, `AzureProvider`. No automatic task-aware routing — model is user-configured per session.

## Security Notes

- `df_transform` sandbox: restricted `exec()` — no file I/O, no network, only pandas/numpy/polars imports
- `sql_query`: parameterized queries only; DML triggers permission check; default read-only
- Secrets: vault integration (`vault://path`) and keyring — never plaintext credentials in settings

## Plugin Directory Convention

```
yigthinker-plugin-name/
  .yigthinker-plugin/plugin.json
  commands/*.md
  hooks/hooks.json
  .mcp.json
  templates/
```

## Session Persistence

Sessions are saved as JSONL transcripts. Resume via `yigthinker --resume`.
