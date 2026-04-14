# P1 Architectural Gap Closure — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Depends on:** P0 arch gaps (completed 2026-04-14, branch `feat/p0-arch-gaps-260414`)

## Scope

6 active items. 2 deferred (Bedrock/Vertex — no current customer demand; Cost tracking — keep current state).

| ID | Item | Complexity | Est. Days |
|----|------|-----------|-----------|
| P1-1 | Streaming tool execution feedback | Medium | 3-4 |
| P1-2 | Session branching + IM session management | Medium-Hard | 5-7 |
| P1-3 | File undo | Easy | 2-3 |
| P1-5 | Richer hook responses | Medium | 3-4 |
| P1-6 | Sub-agent session isolation | Easy | 1-2 |
| P1-7 | MCP Resources support | Easy-Medium | 2-3 |

**Total estimate: ~16-23 days**

---

## P1-1: Streaming Tool Execution Feedback

### Problem

Tools like `sql_query` (20s+ on large tables) and `forecast_timeseries` (Prophet model fitting) run silently. Users in CLI, TUI, and Teams see no signal between "tool started" and "tool finished."

### Design Decision

**Callback injection via SessionContext** (matches Claude Code's pattern).

Agent loop injects a callback before each tool execution. Tools opt in by calling it; most tools ignore it. Tool protocol (`execute(input, ctx) -> ToolResult`) is unchanged.

### Architecture

```
AgentLoop._execute_tool()
  ├── ctx._progress_callback = on_tool_event wrapper
  ├── tool.execute(input, ctx)
  │     └── await ctx.emit_progress("Running SQL...")  # opt-in
  └── ctx._progress_callback = None  # cleanup
```

### Changes

**`yigthinker/session.py`** — Add to `SessionContext`:

```python
_progress_callback: Callable[[str], None] | None = None

async def emit_progress(self, message: str) -> None:
    """Emit a progress message to the UI layer. No-op if no callback set."""
    if self._progress_callback is not None:
        self._progress_callback(message)
```

**`yigthinker/agent.py`** — In `_execute_tool()` / `_execute_tool_batch()`, before calling `tool.execute()`:

```python
if on_tool_event is not None:
    ctx._progress_callback = lambda msg: on_tool_event(
        "tool_progress", {"tool": tool_name, "message": msg}
    )

result = await tool.execute(input_obj, ctx)

ctx._progress_callback = None  # always cleanup
```

**Tools that should emit progress (opt-in, not exhaustive):**

| Tool | Progress messages |
|------|------------------|
| `sql_query` | "Executing query...", "Fetching results..." |
| `forecast_timeseries` | "Fitting model...", "Computing confidence intervals..." |
| `forecast_regression` | "Training regression model..." |
| `report_generate` | "Rendering template...", "Writing PDF..." |
| `workflow_generate` | "Generating workflow template..." |
| `workflow_deploy` | "Deploying to {platform}...", "Verifying deployment..." |

### Surface Integration

| Surface | Delivery mechanism |
|---------|-------------------|
| CLI | `on_token` callback prints `[progress] msg` |
| TUI | WebSocket push via Gateway `on_tool_event` (already wired) |
| Teams | Progress card update (existing `_send_progress_card`) |
| GChat | Text message or card update |
| SDK | `on_tool_event` callback passthrough |

### Constraints

- `emit_progress` is async but the callback itself is sync (fire-and-forget, no awaiting UI response).
- Progress messages are informational only — they do not enter `ctx.messages` or affect LLM context.
- A tool that never calls `emit_progress` behaves identically to today.

---

## P1-2: Session Branching + IM Session Management

### Problem

1. `ctx.messages` is a flat list with no branch points. Users cannot explore alternate analysis paths without losing their current work.
2. In IM channels (Teams, GChat), 1:1 bot conversations have a single thread — users cannot create new sessions or switch between named workspaces.

### Design Decision

**Explicit checkpoint model** — no automatic per-step snapshots, no replay.

Users/code explicitly mark checkpoints. Branching forks from a named checkpoint. IM channels use text commands (`/new`, `/switch`, `/branch`) routed through `SessionKey.named()` (already exists).

### Architecture

#### Checkpoint / Branch (Core)

```
SessionContext
  ├── checkpoint(label: str) -> None
  │     # Stores: {label: CheckpointData(messages=deepcopy, vars=snapshot)}
  ├── branch_from(label: str) -> SessionContext
  │     # Returns new SessionContext restored from checkpoint
  ├── branch() -> SessionContext
  │     # Shorthand: checkpoint("_now") + branch_from("_now")
  └── list_checkpoints() -> list[str]
```

**`CheckpointData`**:

```python
@dataclass
class CheckpointData:
    messages: list[Message]          # deep copy
    vars_snapshot: dict[str, Any]    # {name: df.copy() for DataFrames, ref for others}
    created_at: float                # time.time()
```

**Snapshot cost**: `df.copy(deep=False)` per DataFrame. Pandas 3.x Copy-on-Write ensures safety. Typical session (3-10 small DataFrames) < 10 MB overhead per checkpoint.

**Checkpoint limit**: Default 10 per session (configurable via `settings.json` `session.max_checkpoints`). Oldest evicted when limit reached.

#### IM Session Management

All IM channels parse text commands before routing to AgentLoop:

| Command | Action | SessionKey |
|---------|--------|-----------|
| `/new` | Reset current session (clear messages + vars). If in a named session, resets THAT session — does not switch back to default. | Same key, fresh state |
| `/new <name>` | Create named session | `SessionKey.named(channel, sender, name)` |
| `/switch <name>` | Switch to existing named session | `SessionKey.named(channel, sender, name)` |
| `/branch <name>` | Fork current session into named copy | Checkpoint current + create named |
| `/sessions` | List user's active sessions | N/A (query SessionRegistry) |

**Implementation**: Each channel adapter adds a `_parse_command(text)` method before routing to `handle_message()`. If the text starts with `/new`, `/switch`, `/branch`, or `/sessions`, it's handled by the adapter directly (no AgentLoop involvement).

**User→active_session mapping**: `SessionRegistry` gains a `dict[str, str]` mapping `{sender_key: active_session_key}`. Defaults to `per_sender` key. Updated on `/switch` and `/new <name>`.

### Changes

| File | Change |
|------|--------|
| `session.py` | `CheckpointData` dataclass, `checkpoint()` / `branch_from()` / `branch()` / `list_checkpoints()` methods on `SessionContext` |
| `gateway/session_registry.py` | `active_session` mapping per sender, `reset_session()` method |
| `channels/teams/adapter.py` | `_parse_command()` before `_process_and_respond()` |
| `channels/gchat/adapter.py` | Same `_parse_command()` pattern |
| `channels/feishu/adapter.py` | Same `_parse_command()` pattern |
| `sdk/session.py` | `SDKSession.checkpoint()` / `SDKSession.branch_from()` / `SDKSession.branch()` |
| `settings.py` | `session.max_checkpoints` default 10 |

### Constraints

- Checkpoints are in-memory only — not persisted to disk. Session hibernation does NOT preserve checkpoints (acceptable: checkpoints are exploration aids, not archival).
- `/new` in IM destroys all in-memory state including DataFrames. Bot sends confirmation: "Session cleared. All DataFrames and history removed."
- Branch creates a fully independent session — changes in branch do not affect parent.

---

## P1-3: File Undo

### Problem

`report_generate` and `workflow_generate` create files on disk. Users cannot roll back if results are wrong without manually finding and restoring files.

### Design Decision

**Tool-level file snapshots.** Honest about scope: only local files are undoable. External side effects (RPA deployments, IM messages sent) are explicitly non-reversible.

### Architecture

```python
@dataclass
class UndoEntry:
    tool_name: str
    original_path: Path
    backup_path: Path
    created_at: float
    is_new_file: bool  # True if file didn't exist before (undo = delete)
```

```
SessionContext
  └── undo_stack: list[UndoEntry]  # max 20 entries, oldest evicted
```

**Before writing a file** (in each file-producing tool):

```python
# Use counter suffix to avoid overwriting previous backups of the same file
backup_path = path.parent / f".{path.name}.yig-bak-{len(ctx.undo_stack)}"
if path.exists():
    shutil.copy2(path, backup_path)
    ctx.undo_stack.append(UndoEntry(tool, path, backup_path, time.time(), is_new_file=False))
else:
    ctx.undo_stack.append(UndoEntry(tool, path, Path(""), time.time(), is_new_file=True))
```

**`/undo` command** (parsed in CLI REPL and IM adapters):

```
Undoable files:
  1. report_q1.pdf  (report_generate, 2 min ago)
  2. workflow_daily.json  (workflow_generate, 5 min ago)

Type /undo 1, /undo 2, or /undo all

Note: workflow_daily was deployed to Power Automate. The deployment
itself cannot be rolled back — only the local file is restored.
```

**Undo action**:
- `is_new_file=True`: delete the file
- `is_new_file=False`: restore from `.yig-bak` backup, then delete backup

### Tools That Produce Files

| Tool | File types |
|------|-----------|
| `report_generate` | PDF, Excel, HTML |
| `report_template` | Jinja2 template files |
| `workflow_generate` | Python scripts, JSON configs |
| `workflow_deploy` | Local deployment artifacts |
| `chart_create` | HTML/PNG chart files (if saved to disk) |

### Changes

| File | Change |
|------|--------|
| `session.py` | `UndoEntry` dataclass, `undo_stack: list[UndoEntry]` on `SessionContext` |
| `tools/reports/report_generate.py` | Snapshot before write |
| `tools/workflow/workflow_generate.py` | Snapshot before write |
| `tools/workflow/workflow_deploy.py` | Snapshot before write (local artifacts only) |
| `tools/visualization/chart_create.py` | Snapshot before write (if file output) |
| `cli/repl.py` | `/undo` command handler |
| Channel adapters | `/undo` in `_parse_command()` |

### Helper

A shared utility to avoid repeating snapshot logic in every tool:

```python
# yigthinker/tools/_file_undo.py
def snapshot_before_write(ctx: SessionContext, tool_name: str, path: Path) -> None:
    """Call before writing a file. Handles backup + undo_stack registration."""
```

### Constraints

- Backup files (`.yig-bak`) are cleaned up on session end.
- Undo stack max depth: 20 (configurable). Oldest entries evicted, their backups cleaned up.
- External side effects (workflow deployments, IM messages) are NEVER rolled back. The `/undo` output explicitly lists what cannot be undone.

---

## P1-5: Richer Hook Responses

### Problem

`HookResult` only supports `ALLOW`, `WARN`, and `BLOCK`. Enterprise use cases need:
- RBAC context injection ("user can only access EMEA data")
- PII masking in tool results before LLM sees them
- Suppressing sensitive outputs entirely

### Design Decision

Three new HookResult action types + two-layer configurability (per-hook instance + global capability toggle).

### New HookResult Types

```python
# types.py additions
class HookAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    INJECT_SYSTEM = "inject_system"      # new
    SUPPRESS_OUTPUT = "suppress_output"   # new
    REPLACE_RESULT = "replace_result"     # new

class HookResult:
    # existing
    ALLOW: ClassVar["HookResult"]

    # new classmethods
    @classmethod
    def inject_system(cls, text: str) -> "HookResult":
        """Inject text into LLM system prompt for the next call."""
        r = cls(HookAction.INJECT_SYSTEM, text)
        return r

    @classmethod
    def suppress(cls) -> "HookResult":
        """Suppress tool result — LLM does not see it."""
        return cls(HookAction.SUPPRESS_OUTPUT)

    @classmethod
    def replace(cls, content: Any) -> "HookResult":
        """Replace tool result content with provided value."""
        r = cls(HookAction.REPLACE_RESULT)
        r.replacement = content
        return r
```

### HookExecutor Processing

`HookExecutor.run()` currently returns `HookResult`. This changes to `HookAggregateResult` — a **breaking change** to the return type. All call sites in `agent.py` that check `hook_result.action` must be updated to use `HookAggregateResult` fields. For new action types:

```python
@dataclass
class HookAggregateResult:
    action: HookAction              # highest-priority action (BLOCK > others)
    message: str = ""
    injections: list[str] = field(default_factory=list)   # all inject_system texts
    suppress: bool = False
    replacement: Any = None         # last replace wins
```

Processing order in `agent.py`:
1. **PreToolUse hooks** → can BLOCK, INJECT_SYSTEM
2. Tool executes (if not blocked)
3. **PostToolUse hooks** → can SUPPRESS_OUTPUT, REPLACE_RESULT, INJECT_SYSTEM
4. Agent loop applies:
   - `injections` → appended to system prompt for next LLM call
   - `suppress` → ToolResult not added to `ctx.messages`
   - `replacement` → `tool_result.content = replacement`

### Two-Layer Configurability

**Layer 1 — Hook instance level** (`hooks/hooks.json` or plugin `hooks.json`):

```json
{
  "hooks": [
    {
      "event": "PostToolUse",
      "matcher": "sql_query",
      "command": "mask_pii.sh",
      "enabled": true
    }
  ]
}
```

`HookRegistry.register()` skips entries with `enabled: false`.

**Layer 2 — Global capability toggle** (`settings.json`):

```json
{
  "hooks": {
    "capabilities": {
      "inject_system": true,
      "suppress_output": true,
      "replace_result": true
    }
  }
}
```

When a capability is globally disabled, `HookExecutor` downgrades that action type to `ALLOW` (hook still runs, but its special effect is suppressed).

### Safety Guard

Injected system text is capped at 2048 tokens total (across all hooks). If cumulative injections exceed this, excess is truncated and a warning is logged. This prevents runaway hooks from blowing the context budget.

### Changes

| File | Change |
|------|--------|
| `types.py` | New `HookAction` values, new `HookResult` classmethods, `HookAggregateResult` dataclass |
| `hooks/executor.py` | Aggregate logic for new action types, capability gate check |
| `hooks/registry.py` | `enabled` field support on registration |
| `agent.py` | Handle `HookAggregateResult.injections` / `.suppress` / `.replacement` after tool execution |
| `settings.py` | `hooks.capabilities` defaults (all true) |

### Constraints

- `inject_system` texts are ephemeral — they apply to the NEXT LLM call only, not persisted.
- `replace_result` and `suppress_output` are PostToolUse only. Using them in PreToolUse is a no-op (tool hasn't produced a result yet).
- Multiple hooks returning `replace_result`: last hook wins (hooks run in registration order).
- `suppress_output` takes priority over `replace_result` — if any hook suppresses, the result is not shown regardless of replacements.

---

## P1-6: Sub-agent Session Isolation

### Problem

Two minor gaps in the current (already well-designed) sub-agent isolation:

1. Background sub-agents hold a live reference to `parent_vars` (`ctx.vars`). If the parent session is evicted/hibernated by the Gateway while the child is running, `merge_back_dataframes` writes to a stale object.
2. No `dataframes="*"` shorthand for copying all parent DataFrames to the child.

### Design Decision

Two targeted patches. No architectural change.

### Patch 1: Safe merge-back for background sub-agents

Instead of capturing `parent_vars = ctx.vars` directly, capture the session key and look up the live session at merge time:

```python
# In spawn_agent.py background mode, replace:
parent_vars = ctx.vars

# With:
parent_session_key = ctx.session_id
session_registry = getattr(ctx, '_session_registry', None)

async def _run_background() -> None:
    ...
    # At merge time:
    if session_registry is not None:
        live_session = session_registry.get(parent_session_key)
        if live_session is None:
            logger.warning("Parent session evicted, skipping DataFrame merge-back")
            return
        target_vars = live_session.ctx.vars
    else:
        target_vars = parent_vars  # CLI mode fallback (no registry)

    merge_back_dataframes(target_vars, child_ctx.vars, agent_name, original_names)
```

**Gateway wiring**: `GatewayServer.handle_message()` sets `ctx._session_registry = self._registry` before calling `agent_loop.run()`.

### Patch 2: `dataframes="*"` wildcard

```python
# In spawn_agent.py:
if input.dataframes == ["*"]:
    all_names = [info.name for info in ctx.vars.list()]
    copy_dataframes_to_child(ctx.vars, child_ctx.vars, all_names)
    original_names = set(all_names)
```

`SpawnAgentInput.dataframes` already accepts `list[str] | None`. Wildcard is just convention: `["*"]` means "all."

### Changes

| File | Change |
|------|--------|
| `tools/spawn_agent.py` | Safe merge-back via session lookup; `["*"]` wildcard handling |
| `gateway/server.py` | Set `ctx._session_registry` before `agent_loop.run()` |
| `subagent/dataframes.py` | No change needed |

### Constraints

- CLI mode (no Gateway, no SessionRegistry): falls back to direct `parent_vars` reference (current behavior). This is safe because CLI mode has no session eviction.
- `["*"]` copies all vars at spawn time. Vars created by the parent AFTER spawn are not visible to the child (snapshot semantics, consistent with explicit copy).

---

## P1-7: MCP Resources Support

### Problem

MCP spec defines `resources/list` and `resources/read` for exposing structured data (files, DB schemas, API specs) to the LLM. Current `MCPClient` only supports `tools/list` and `tools/call`.

### Design Decision

**On-demand tool approach** — two dynamically registered tools. LLM decides when to read a resource.

### Architecture

```
MCPLoader.load()
  ├── tools/list → register as _MCPToolWrapper (existing)
  └── resources/list → if any resources exist:
        register mcp_list_resources tool
        register mcp_read_resource tool
```

### New Tools

**`mcp_list_resources`**:

```python
class MCPListResourcesInput(BaseModel):
    server: str | None = None  # filter by server name; None = all servers

class MCPListResourcesTool:
    name = "mcp_list_resources"
    description = "List available MCP resources across connected servers."
    input_schema = MCPListResourcesInput
```

Returns:
```json
[
  {"uri": "file:///data/schema.sql", "name": "Database Schema", "server": "my-server"},
  {"uri": "db://main/users", "name": "Users table", "server": "my-server"}
]
```

**`mcp_read_resource`**:

```python
class MCPReadResourceInput(BaseModel):
    uri: str  # resource URI from mcp_list_resources

class MCPReadResourceTool:
    name = "mcp_read_resource"
    description = "Read the contents of an MCP resource by URI."
    input_schema = MCPReadResourceInput
```

Returns the resource content as text or structured data (whatever the MCP server provides).

### MCPClient Changes

```python
class MCPClient:
    # existing
    async def list_tools(self) -> list[dict]: ...
    async def call_tool(self, name, args) -> Any: ...

    # new
    async def list_resources(self) -> list[dict]:
        """Call resources/list on the MCP server."""

    async def read_resource(self, uri: str) -> Any:
        """Call resources/read on the MCP server."""
```

### MCPLoader Changes

During `load()`, after loading tools:

```python
# For each MCP server:
resources = await client.list_resources()
if resources:
    self._resource_clients[server_name] = client
    # Register tools only once (not per-server)
    if not self._resources_tools_registered:
        registry.register(MCPListResourcesTool(self._resource_clients))
        registry.register(MCPReadResourceTool(self._resource_clients))
        self._resources_tools_registered = True
```

The resource tools hold a reference to `_resource_clients` dict to route requests to the correct MCP server based on URI prefix or server name.

### Changes

| File | Change |
|------|--------|
| `mcp/client.py` | `list_resources()` / `read_resource()` methods |
| `mcp/loader.py` | Resource discovery during `load()`, conditional tool registration |
| `mcp/resource_tools.py` | New file: `MCPListResourcesTool` + `MCPReadResourceTool` |

### Constraints

- Resource tools are only registered if at least one MCP server reports resources. If no servers have resources, no tools are added (zero overhead).
- Resource URI routing: each MCP server's resources are cached at load time with their server name. `mcp_read_resource` looks up the URI in this cache to find the owning server. If URI is not found in cache, `list_resources()` is re-called (lazy refresh). If still not found, returns error.
- Resources are read-only. There is no `resources/write` in the MCP spec.

---

## Deferred Items

### P1-4: Bedrock / Vertex Providers — DEFERRED

Current target customers use Azure only (AzureProvider already implemented). Bedrock and Vertex follow the same `LLMProvider` Protocol pattern — mechanical SDK substitution when customer demand arises.

### P1-8: Cost Tracking — DEFERRED

Keep current `StatsAccumulator` state. LLM providers do not yet return token counts in `LLMResponse`. Revisit when token usage visibility becomes a customer requirement.

---

## Cross-Cutting Concerns

### IM Command Parsing

P1-2, P1-3, and P1-1 all add text commands parsed by channel adapters. These should share a single `_parse_command()` implementation:

```python
# channels/command_parser.py
@dataclass
class ChannelCommand:
    name: str            # "new", "switch", "branch", "undo", "sessions"
    args: list[str]      # remaining tokens
    raw_text: str        # original message text

def parse_channel_command(text: str) -> ChannelCommand | None:
    """Parse /command from message text. Returns None if not a command."""
```

All three adapters (Teams, GChat, Feishu) call `parse_channel_command()` before routing to `handle_message()`.

### Settings Additions

```json
{
  "session": {
    "max_checkpoints": 10
  },
  "undo": {
    "max_stack_depth": 20
  },
  "hooks": {
    "capabilities": {
      "inject_system": true,
      "suppress_output": true,
      "replace_result": true
    }
  }
}
```

### Dependency on P0

All P1 items assume P0 changes are merged. Specifically:
- P1-1 depends on P0's `on_tool_event` callback wiring
- P1-5 depends on P0-3's enriched plugin hook loading
- P1-7 depends on P0-2's multi-transport MCPClient
- P1-6 references `SubagentEngine` from P0 spawn_agent improvements

---

## Implementation Order

Recommended sequence (respects dependencies):

1. **P1-6** (sub-agent isolation) — smallest, no dependencies on other P1 items
2. **P1-1** (streaming feedback) — foundational for UX; other items benefit from progress reporting
3. **P1-5** (hook enrichment) — extends types.py; P1-3 can use hooks for undo tracking
4. **P1-3** (file undo) — independent after P1-5
5. **P1-7** (MCP resources) — independent, touches MCP layer only
6. **P1-2** (session branching + IM commands) — largest; benefits from all prior items being stable
