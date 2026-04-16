# Yigthinker — Developer Context

## What This Is

Yigthinker is a Python-based AI agent for financial and data analysis with workflow automation. It uses a flat tool registry (30 tools), a single agent loop, a hook system for cross-cutting concerns, a permission system, MCP integration for external systems, a plugin system, and a workflow generation/deployment layer — all adapted for in-memory DataFrame operations on financial data. Repeatable analysis patterns become automated workflows deployed to RPA platforms (Power Automate, UiPath) or local OS schedulers.

Design specs:
- Original: `docs/superpowers/specs/2026-04-01-yigthinker-design.md`
- Workflow & RPA Bridge: `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md`

## Architecture Principles

- **Flat tools** — all 30 tools registered directly in the Agent Loop; no grouping or agent personas at runtime
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

All tools: `sql_query`, `sql_explain`, `schema_inspect`, `df_load`, `df_transform`, `df_profile`, `df_merge`, `chart_create`, `chart_modify`, `chart_recommend`, `report_generate`, `report_template`, `report_schedule`, `forecast_timeseries`, `forecast_regression`, `forecast_evaluate`, `explore_overview`, `explore_drilldown`, `explore_anomaly`, `finance_calculate`, `finance_analyze`, `finance_validate`, `finance_budget`, `spawn_agent`, `agent_status`, `agent_cancel`, `workflow_generate`, `workflow_deploy`, `workflow_manage`, `suggest_automation`

## Hook Pattern

```python
@hook("PreToolUse", matcher="sql_query|df_transform")
async def my_hook(event: HookEvent) -> HookResult:
    return HookResult.ALLOW  # or .BLOCK("reason") or .WARN("message")
```

Command hooks use exit codes: 0 = allow, 1 = warn user only, 2 = block (stderr → LLM feedback).

Hook events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`, `PreCompact`, `SubagentStop`

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
7. end_turn → CLI output + WebSocket push to connected clients

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
- Workflow templates: Jinja2 `SandboxedEnvironment` + AST validation (two-layer SSTI prevention)
- Workflow scripts: self-contained, never import Yigthinker; credential placeholders use `vault://` references

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

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Yigthinker**

Yigthinker is a Python-based AI agent for financial and data analysis with workflow automation — a headless "data analysis Claude Code" with multi-channel access. It uses a flat tool registry (30 tools), a single Agent Loop, hooks for cross-cutting concerns, and in-memory DataFrame operations. The codebase includes Gateway daemon (with RPA self-healing endpoints), Textual TUI, channel adapters (Teams integrated; Feishu/Google Chat adapters exist but are not yet formally validated), and two independent MCP server packages for UiPath and Power Automate. No web dashboard — product is headless by design.

**Core Value:** A user can interact via CLI REPL, IM channels (Teams), or TUI connected to the Gateway, having AI-assisted data analysis conversations with tool calls (SQL, DataFrame, charts, forecasts, finance calculations) — same agent, multiple surfaces. Repeatable analysis patterns become automated workflows deployed to RPA platforms.

### Constraints

- **Tech stack**: Python 3.11, existing dependencies (FastAPI, Textual, Typer, Pydantic, Jinja2, etc.)
- **Platform**: Must work on Windows (no fork(), gateway runs foreground with --fg)
- **Bottom-up order**: Agent Loop → Gateway → TUI → Channels (dependency chain)
- **All 4 providers**: Claude, OpenAI, Ollama, Azure must all work
- **Self-contained scripts**: Generated workflows must run without Yigthinker installed
- **Gateway optional**: Scripts must function with Gateway offline (lose self-healing only)
- **MCP independence**: MCP server packages are separate packages, not bundled into core
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - All source code (`yigthinker/`, `tests/`)
## Runtime
- CPython 3.11.9 (installed at `C:\Program Files\Python311`)
- pip / hatchling build backend
- Lockfile: Not present (uses virtual environment at `.venv/`)
- Build config: `pyproject.toml` with `[build-system] requires = ["hatchling"]`
## Frameworks
- typer 0.24.1 - CLI entrypoint and command definitions (`yigthinker/__main__.py`)
- rich 14.3.3 - Terminal output formatting, tables, panels (`yigthinker/cli/`)
- pydantic 2.12.5 - Tool input schemas, data models (`yigthinker/types.py`, all tool files)
- fastapi 0.135.3 - Gateway daemon REST API + WebSocket server (`yigthinker/gateway/server.py`)
- uvicorn 0.42.0 - ASGI server for FastAPI apps (launched via `yigthinker gateway start`)
- pandas 3.0.2 - Primary DataFrame operations across all tools
- numpy 2.4.4 - Numerical operations in forecast tools
- sqlalchemy 2.0.48 - Async database access via `AsyncEngine` (`yigthinker/tools/sql/connection.py`)
- aiosqlite 0.22.1 - SQLite async driver (used as default database + event dedup store)
- plotly 6.6.0 - Chart generation via `plotly.express` and `plotly.graph_objects` (`yigthinker/tools/visualization/chart_create.py`)
- textual 8.2.1 - Terminal UI application (`yigthinker/tui/app.py` and `yigthinker/tui/`)
- websockets 16.0 - WebSocket client for TUI-to-Gateway connection (`yigthinker/tui/ws_client.py`)
- pytest 9.0.2 - Test runner (`pyproject.toml` `testpaths = ["tests"]`)
- pytest-asyncio 1.3.0 - Async test support (`asyncio_mode = "auto"`)
- pytest-mock 3.15.1 - Mocking helpers
## Key Dependencies
- `anthropic` 0.88.0 - Anthropic Claude API client (`yigthinker/providers/claude.py`); default LLM provider
- `openai` 2.30.0 - OpenAI + Azure OpenAI client (`yigthinker/providers/openai.py`, `yigthinker/providers/azure.py`)
- `httpx` 0.28.1 - HTTP client used by Ollama provider and gateway status command
- `filelock` 3.25.2 - File-based locking for AutoDream memory consolidation (`yigthinker/memory/auto_dream.py`)
- `openpyxl` 3.1.5 - Excel file read/write support for `df_load` tool
- `reportlab` 4.4.10 - PDF report generation for `report_generate` tool
- `pyarrow` 23.0.1 - Parquet serialization for session hibernation (`yigthinker/gateway/hibernation.py`)
- `prophet` (not installed in current venv) - Time series forecasting, falls back gracefully to statsmodels
- `statsmodels` (not installed in current venv) - Exponential smoothing forecasting (`yigthinker/tools/forecast/forecast_timeseries.py`)
- `scikit-learn` (not installed in current venv) - Regression forecasting (`yigthinker/tools/forecast/forecast_regression.py`)
- `lark-oapi` 1.5.3 - Feishu/Lark SDK (`yigthinker/channels/feishu/adapter.py`)
- `msal` 1.35.1 - Microsoft Azure AD token acquisition for Teams (`yigthinker/channels/teams/adapter.py`)
- `google-api-python-client` 2.193.0, `google-auth` 2.49.1 - Google Chat API (`yigthinker/channels/gchat/adapter.py`)
- `mcp` (SDK) - Model Context Protocol client; loaded lazily in `yigthinker/mcp/client.py` via `from mcp import ClientSession, StdioServerParameters`; missing package is caught silently at startup
- `jinja2` >=3.1.6 - Sandboxed template rendering for workflow code generation (CVE-2025-27516 fix)
- `croniter` >=6.0.0 - Cron expression parsing for workflow scheduling
## Configuration
- `ANTHROPIC_API_KEY` - Required for Claude models (`claude-*`)
- `OPENAI_API_KEY` - Required for OpenAI models (`gpt-*`, `o1`, `o3`, `o4`)
- `AZURE_OPENAI_API_KEY` - Required for Azure deployments (`azure/`)
- Ollama requires no key (uses local HTTP at `http://localhost:11434`)
- Default model: `claude-sonnet-4-20250514`
- Ollama base URL: `http://localhost:11434`
- Gateway: `127.0.0.1:8766`
- Session transcripts: `~/.yigthinker/sessions/*.jsonl`
- Session hibernation: `~/.yigthinker/hibernate/`
- Gateway token: `~/.yigthinker/gateway.token`
- Azure API version: `2024-02-01`
- `pyproject.toml` - Project manifest; optional dependency groups: `dev`, `forecast`, `gateway`, `tui`, `feishu`, `teams`, `gchat`, `all-channels`
- CLI entrypoint: `yigthinker = "yigthinker.__main__:app"`
- No `.env` file present; no `.nvmrc` or `.python-version`
## Platform Requirements
- Python 3.11+
- Virtual environment at `.venv/`
- Install with `pip install -e .[dev]` (core + dev extras)
- Optional extras: `pip install -e .[forecast,gateway,tui,rpa-uipath,rpa-powerautomate]`
- Self-hosted; no cloud platform dependency
- Can run headless as gateway daemon: `yigthinker gateway start`
- Supports local Ollama for air-gapped deployments
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case` for all Python files: `forecast_timeseries.py`, `df_transform.py`, `auto_dream.py`
- Tool files are named identically to the tool name string: `sql_query.py` exports `SqlQueryTool` with `name = "sql_query"`
- Test files mirror source structure: `yigthinker/tools/forecast/forecast_evaluate.py` → `tests/test_tools/test_forecast_evaluate.py`
- `PascalCase` for all classes: `AgentLoop`, `SessionContext`, `ForecastTimeseriesTool`, `VarRegistry`
- Tool classes: `{CapitalizedToolName}Tool` — e.g. `DfTransformTool`, `SqlQueryTool`, `ForecastEvaluateTool`
- Input schema classes: `{CapitalizedToolName}Input` — e.g. `DfTransformInput`, `ForecastRegressionInput`
- Protocol classes: named for the abstraction, not for an implementation: `LLMProvider`, `YigthinkerTool`
- `snake_case` for all functions and methods: `should_run()`, `list_sessions_since_last()`, `provider_from_settings()`
- Private helpers prefixed with `_`: `_deep_merge`, `_safe_import`, `_check_ast`, `_DML_KEYWORDS`, `_BLOCKED_DUNDERS`
- Module-level private helpers are prefixed with `_`: `_LOADERS`, `_SAMPLE_ROWS`, `_SAFE_BUILTINS`
- Async methods are `async def` throughout; no mixing of sync and async in the same call path
- `snake_case`: `tool_name`, `input_obj`, `result_df`, `forecast_df`
- Type-annotated consistently: `list[str]`, `dict[str, Any]`, `Path | None`
- Defined at module level with `TypeAlias` or plain assignment: `PermissionDecision = Literal["allow", "ask", "deny"]`, `HookFn = Callable[[HookEvent], Awaitable[HookResult]]`
## Code Style
- No formatter config file detected (no `.ruff.toml`, `.black`, `.prettierrc`)
- Code consistently uses 4-space indentation
- Line length appears to stay well under 120 characters
- Trailing commas used in multi-line collection literals
- No linter config detected in `pyproject.toml`
- `# noqa: S102` used on the intentional `exec()` call in `yigthinker/tools/dataframe/df_transform.py:111`
- `# type: ignore[import]` used on optional dependency imports (prophet, sklearn) and SDK quirks
- `# type: ignore[arg-type]` used where SDK types diverge from internal types (claude.py, openai.py)
## Future Annotations
## Import Organization
## Tool Implementation Pattern
- `tool_use_id` is always set to `""` in the `execute()` return — the agent loop fills it in after the fact (`result.tool_use_id = tool_use_id`)
- Tools that need an injected dependency (e.g. `ConnectionPool`) take it in `__init__`; stateless tools have no `__init__`
- Result content is either a plain `str` or a `dict` — never a custom object
## Error Handling
## Logging
## Comments
- Short single-sentence docstrings on classes that need explanation: `VarRegistry`, `HookExecutor`, `ContextManager`, `PermissionSystem`
- No docstrings on tool classes — the `description` attribute serves as the LLM-facing description
- No method-level docstrings on simple getters/setters
- Used sparingly for non-obvious logic: `# Fall through to statsmodels`, `# Confidence interval approximation: ±1.96 * residual std`
- `noqa` and `type: ignore` always include a code or reason: `# noqa: S102`, `# type: ignore[import]`
- Used on test files only to explain the test scenario: `tests/test_integration.py`, `tests/test_e2e_simulation.py`
- Not used on source module files
## Function Design
## Module Design
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- One `AgentLoop` orchestrates all tool execution — no sub-agents, no hierarchical planner at runtime
- All 30 tools registered at the same level in a flat `ToolRegistry`; no grouping or routing by tool category
- `SessionContext` holds the only persistent in-memory state between tool calls (message history + DataFrame variable registry)
- Cross-cutting concerns (permissions, audit, RBAC) are implemented as Hook functions, not as architectural layers
- Multiple input surfaces (CLI REPL, Gateway daemon + WebSocket, messaging channel adapters) all funnel into the same `AgentLoop.run()` call
## Layers
- Purpose: Accept user input from any surface, build `SessionContext`, invoke `AgentLoop.run()`
- Locations:
- Depends on: AgentLoop, SessionContext, PluginLoader, Settings
- Purpose: Drive the LLM ↔ tool-call cycle until `end_turn`; enforce hooks and permissions before each tool call
- Location: `yigthinker/agent.py`
- Contains: `AgentLoop` class with `run()` and `_execute_tool()` methods
- Depends on: `LLMProvider`, `ToolRegistry`, `HookExecutor`, `PermissionSystem`, `SessionContext`
- Used by: CLI REPL, Gateway `handle_message()`, single-shot query path in `__main__._run_query()`
- Purpose: Abstract LLM API differences behind a uniform `chat()` interface
- Location: `yigthinker/providers/`
- Contains: `LLMProvider` Protocol (`base.py`), `ClaudeProvider`, `OpenAIProvider`, `OllamaProvider`, `AzureProvider`, `factory.py`
- Depends on: `anthropic`, `openai` SDKs
- Used by: `AgentLoop`
- Purpose: Implement all domain capabilities as independently executable tools
- Location: `yigthinker/tools/`
- Contains: 30 registered tools across subgroups (`sql/`, `dataframe/`, `visualization/`, `reports/`, `forecast/`, `exploration/`, `finance/`, `workflow/`, `spawn_agent.py`)
- Depends on: `SessionContext` (for `ctx.vars` access), `ContextManager` (for result summarization)
- Used by: `AgentLoop._execute_tool()`
- Purpose: Hold all session-scoped mutable state — message history, DataFrame registry, stats, settings reference
- Location: `yigthinker/session.py`
- Contains: `SessionContext` dataclass, `VarRegistry` (in-memory DataFrame store), `StatsAccumulator`
- Depends on: `yigthinker/stats.py`, `yigthinker/types.py`
- Used by: Every tool `execute()`, `AgentLoop.run()`, `Repl`, `GatewayServer`
- Purpose: Intercept tool calls for auditing, blocking, or warnings without modifying core logic
- Location: `yigthinker/hooks/`, `yigthinker/permissions.py`
- Contains: `HookRegistry` (stores `(event_type, matcher, fn)` tuples), `HookExecutor` (runs hooks for an event), `PermissionSystem` (allow/ask/deny rule evaluation)
- Depends on: `yigthinker/types.py` (`HookEvent`, `HookResult`, `HookAction`)
- Used by: `AgentLoop._execute_tool()`
- Purpose: Load and merge layered config (defaults → project → user → managed)
- Location: `yigthinker/settings.py`
- Contains: `load_settings()`, `DEFAULT_SETTINGS` dict, `has_api_key()`, `_deep_merge()`
- Depends on: Python stdlib only
- Used by: `__main__.main()`, `GatewayServer`
- Purpose: JSONL transcript write/read for session resume
- Location: `yigthinker/persistence.py`
- Contains: `TranscriptWriter`, `TranscriptReader`, `find_latest_session()`
- Used by: `Repl`, `__main__._hydrate_session_from_resume()`
- Purpose: Multi-session lifecycle management for the daemon mode (create, evict, hibernate, restore)
- Location: `yigthinker/gateway/session_registry.py`, `yigthinker/gateway/hibernation.py`
- Contains: `SessionRegistry`, `ManagedSession` (wraps `SessionContext` + `asyncio.Lock` + idle tracking)
- Used by: `GatewayServer`
- Purpose: Periodic session consolidation ("dreaming") and compact-for-context operations
- Location: `yigthinker/memory/`
- Contains: `AutoDream`, `DreamState`, `compact.py`, `session_memory.py`
- Used by: Triggered optionally; guarded by `gates.py` feature flags
- Purpose: Load external tools from MCP servers defined in `.mcp.json` and inject them into `ToolRegistry`
- Location: `yigthinker/mcp/`
- Contains: `MCPLoader`, `MCPClient`, `_MCPToolWrapper` (adapts MCP tool to `YigthinkerTool` protocol)
- Used by: `__main__._build()` at startup
- Purpose: Discover plugins from well-known dirs and load their slash commands as Markdown files
- Location: `yigthinker/plugins/`
- Contains: `PluginLoader`, `PluginManifest`, `SlashCommand`, `load_commands_from_dir()`
- Used by: `__main__.main()`
- Purpose: Generate, deploy, and manage automated workflows from analysis conversations
- Location: `yigthinker/tools/workflow/`
- Contains: `workflow_generate`, `workflow_deploy`, `workflow_manage`, `suggest_automation` tools; `TemplateEngine` (Jinja2 sandbox), `WorkflowRegistry` (file-based JSON), `pa_bundle.py`, `uipath_bundle.py`, `mcp_detection.py`
- Depends on: `SessionContext`, `PatternStore`, Jinja2 SandboxedEnvironment
- Used by: `AgentLoop._execute_tool()`
- Purpose: Self-healing callback and status reporting for RPA-deployed workflows
- Location: `yigthinker/gateway/rpa_controller.py`, `yigthinker/gateway/rpa_state.py`
- Contains: `RPAController` (LLM-driven error classification: fix_applied/skip/escalate), `RPAStateStore` (sqlite3 dedup + circuit breaker)
- Depends on: `LLMProvider`, `GatewayServer`
- Used by: Gateway routes `/api/rpa/callback`, `/api/rpa/report`
- Purpose: Async app initialization — builds AgentLoop, ToolRegistry, ConnectionPool from settings
- Location: `yigthinker/builder.py`
- Contains: `build()` async factory; initializes optional subsystems (memory, patterns, RPA state, workflow registry)
- Used by: `__main__._build()`, `GatewayServer`
- Purpose: Cross-session automation pattern detection and proactive suggestion suppression
- Location: `yigthinker/memory/patterns.py`
- Contains: `PatternStore` with filelock + atomic writes, TTL-based suppression expiry, lazy pruning
- Used by: `AutoDream` (BHV-05), `suggest_automation` tool (BHV-03)
- Purpose: Feature flag system for gating optional subsystems
- Location: `yigthinker/gates.py`
- Contains: `is_enabled(gate_name, settings)` — checks env vars (`YIGTHINKER_GATE_<NAME>`) and settings
- Gates: session_memory, auto_dream, speculation, agent_teams, advisor, voice, behavior
- Used by: `builder.py`, `AgentLoop`, `registry_factory.py`
## Data Flow
- `ctx.vars` (`VarRegistry`) — in-memory DataFrames, persists for entire session lifetime
- `ctx.messages` — full conversation history in `AgentLoop` message format
- Large DataFrames (> 10 rows): `ContextManager.summarize_dataframe_result()` returns summary to LLM; full data stays in `ctx.vars` only
- Session persistence: JSONL transcript at `~/.yigthinker/sessions/session-<timestamp>-<id>.jsonl`
- Gateway hibernation: `SessionHibernator` serializes `ManagedSession` to `~/.yigthinker/hibernate/`
## Key Abstractions
- Purpose: Uniform interface for all 30 tools; enables `ToolRegistry` to store heterogeneous tools
- Location: `yigthinker/tools/base.py`
- Pattern: Structural `Protocol` — any class with `name: str`, `description: str`, `input_schema: type[BaseModel]`, and `async execute(input, ctx) -> ToolResult` satisfies it
- Purpose: Swap LLM backends without touching `AgentLoop`
- Location: `yigthinker/providers/base.py`
- Pattern: `Protocol` with single `async chat(messages, tools, system) -> LLMResponse` method
- Purpose: Uniform interface for messaging platform integrations
- Location: `yigthinker/channels/base.py`
- Pattern: `Protocol` with `start(gateway)`, `stop()`, `session_key(event)`, `send_response(event, text)` methods
- Purpose: Session-scoped named store for DataFrames and chart artifacts — the deliberate deviation from standard agent patterns
- Location: `yigthinker/session.py`
- Pattern: `ctx.vars.set("name", df)` / `ctx.vars.get("name")` / `ctx.vars.list()` — tools use this to pass data between calls
- Purpose: Typed return from hook functions with three possible actions
- Location: `yigthinker/types.py`
- Pattern: `HookResult.ALLOW` (singleton), `HookResult.warn("msg")`, `HookResult.block("reason")` (class methods)
- Purpose: Gateway-level wrapper adding per-session concurrency guard and lifecycle metadata to `SessionContext`
- Location: `yigthinker/gateway/session_registry.py`
- Pattern: `asyncio.Lock` field; `GatewayServer.handle_message()` always uses `async with session.lock`
## Entry Points
- Location: `yigthinker/__main__.py` → `main()` decorated with `@app.command()`
- Triggers: `yigthinker [query]` or `yigthinker` (REPL)
- Responsibilities: Load settings, ensure API key, build `AgentLoop` via `_build()`, run single query or hand off to `Repl`
- Location: `yigthinker/__main__.py` → `setup()` + `yigthinker/cli/setup_wizard.py`
- Triggers: `yigthinker setup`
- Responsibilities: Interactive provider/model/API key configuration
- Location: `yigthinker/__main__.py` → `gateway_start()` + `yigthinker/gateway/server.py`
- Triggers: `yigthinker gateway start`
- Responsibilities: Start `GatewayServer` (FastAPI) on port 8766; mounts `/ws`, `/api/sessions`, `/health`, channel webhook routes
- Location: `yigthinker/__main__.py` → `tui()` + `yigthinker/tui/app.py`
- Triggers: `yigthinker tui`
- Responsibilities: Launch Textual TUI that connects to gateway via WebSocket
- Location: `yigthinker/agent.py`
- Triggers: Called by REPL, single-query path, `GatewayServer.handle_message()`
- Responsibilities: Entire LLM ↔ tool-call loop
## Error Handling
- `AgentLoop._execute_tool()` wraps `tool.execute()` in `try/except Exception` → `ToolResult(is_error=True, content=str(exc))`
- Hook BLOCK results short-circuit tool execution and return `ToolResult(is_error=True, content="Blocked: ...")` to LLM
- Permission deny returns `ToolResult(is_error=True, content="Permission denied...")`
- Individual tools catch domain-specific exceptions (e.g. `KeyError` from `ctx.vars.get()`, `sa.exc.*` from SQLAlchemy) and return `ToolResult(is_error=True)`
- `AutoDream._do_dream()` suppresses all exceptions via bare `except Exception: pass` — background operations never surface to user
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

## Phase 0: Teams Excel Delivery (Action-First Behavior)

Yigthinker's agent loop defaults to ACTION, not EXPLANATION. The
`BASE_SYSTEM_PROMPT` in `yigthinker/prompts/base.py` is always prepended
to the system message before any dynamic content (memory, directives,
hooks, steerings). This anchors the LLM to produce artifacts (files,
charts, tables) rather than tutorials.

**Key files:**
- `yigthinker/prompts/base.py` — the base prompt, single source of truth
- `yigthinker/agent.py` — prepends the base prompt at every iteration

**Regression guard:** `pytest tests/test_e2e_teams_excel.py`

**User-scenario acceptance:** `docs/user-scenarios/phase0-teams-excel.md`

Changing the base prompt or removing it from the assembly will break the
E2E test. This is by design — the action-first contract is the product.
