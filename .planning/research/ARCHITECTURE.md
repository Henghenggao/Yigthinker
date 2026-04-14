# Architecture Patterns: Workflow & RPA Bridge Integration

> **Status:** Pre-implementation research for v1.1. v1.1 shipped 2026-04-12. This document is a historical reference — consult shipped code and phase summaries for current state.

**Domain:** Workflow generation, RPA deployment, and lifecycle management integrated into existing AI agent
**Researched:** 2026-04-09
**Confidence:** HIGH (existing codebase fully analyzed, design spec verified against actual code)

---

## Recommended Architecture

The v1.1 milestone adds workflow/RPA capabilities to Yigthinker by following the existing architectural patterns exactly: flat tools in the registry, hooks for cross-cutting concerns, Gateway route additions for external callbacks, and independent MCP server packages for RPA platform APIs. No new architectural layers are introduced.

### Integration Strategy: New vs Modified

| Component | Status | Files |
|-----------|--------|-------|
| 3 workflow tools | **NEW** | `yigthinker/tools/workflow/workflow_generate.py`, `workflow_deploy.py`, `workflow_manage.py` |
| Workflow Registry | **NEW** | `yigthinker/tools/workflow/registry.py` |
| Jinja2 templates | **NEW** | `yigthinker/tools/workflow/templates/**/*.j2` |
| Checkpoint utils template | **NEW** | `yigthinker/tools/workflow/templates/base/checkpoint_utils.py.j2` |
| Behavior directive constant | **NEW** | `yigthinker/tools/workflow/behavior.py` |
| SessionStart health check hook | **NEW** | `yigthinker/hooks/workflow_health.py` |
| Gateway RPA callback endpoint | **NEW** | `yigthinker/gateway/rpa_callback.py` |
| Gateway RPA report endpoint | **NEW** | `yigthinker/gateway/rpa_report.py` |
| MCP PA server | **NEW** (independent package) | `yigthinker-mcp-powerautomate/` |
| MCP UiPath server | **NEW** (independent package) | `yigthinker-mcp-uipath/` |
| Tool registry factory | **MODIFIED** (add optional param + 3 registrations) | `yigthinker/registry_factory.py` |
| Gateway server | **MODIFIED** (mount 2 new routes, store WorkflowRegistry ref) | `yigthinker/gateway/server.py` |
| Builder | **MODIFIED** (create registry, register hook, set directive) | `yigthinker/builder.py` |
| Agent loop | **MODIFIED** (read system_inject + workflow directive) | `yigthinker/agent.py` |
| Session context | **MODIFIED** (add system_inject field) | `yigthinker/session.py` |
| Hook event | **MODIFIED** (add optional ctx field) | `yigthinker/types.py` |
| pyproject.toml | **MODIFIED** (add `workflow` optional dep group) | `pyproject.toml` |

**Key insight:** Only 6 existing files need modification, and each modification is small (1-15 lines). Everything else is additive. This is the correct integration pattern for Yigthinker -- the architecture was designed for this kind of extension.

---

## Component Boundaries

### Layer 1: Workflow Tools (Native, in-process)

Three new tools registered flat alongside the existing 26. They follow the identical `YigthinkerTool` Protocol pattern.

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `WorkflowGenerateTool` | Generate Python scripts from step definitions via Jinja2 templates | `ctx.vars` (read DataFrame schemas), `WorkflowRegistry` (write manifest), filesystem (write scripts) |
| `WorkflowDeployTool` | Deploy generated scripts to RPA platforms or local OS scheduler | `WorkflowRegistry` (read/write), filesystem (write guided artifacts). Returns plan for LLM to call MCP tools in `auto` mode |
| `WorkflowManageTool` | Lifecycle operations: list, inspect, pause, resume, rollback, retire, health_check | `WorkflowRegistry` (read/write). Returns plan for LLM to call MCP tools for pause/resume triggers |

**Dependency injection pattern:** The workflow tools need access to the `WorkflowRegistry`. Following the existing pattern (e.g., `SqlQueryTool(pool=pool)`, `SpawnAgentTool` getting `_tools` reference), the registry is injected via `__init__`:

```python
class WorkflowGenerateTool:
    name = "workflow_generate"
    description = "Generate a self-contained Python script from step definitions..."
    input_schema = WorkflowGenerateInput

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry

    async def execute(self, input: WorkflowGenerateInput, ctx: SessionContext) -> ToolResult:
        # 1. Read DataFrame schemas from ctx.vars for column awareness
        # 2. Render Jinja2 templates
        # 3. Write to versioned directory
        # 4. Update registry
        ...
```

**Registration in `registry_factory.py`:**

```python
def build_tool_registry(
    pool: ConnectionPool,
    workflow_registry: "WorkflowRegistry | None" = None,
) -> ToolRegistry:
    # ... existing 26 tools ...

    if workflow_registry is not None:
        from yigthinker.tools.workflow.workflow_generate import WorkflowGenerateTool
        from yigthinker.tools.workflow.workflow_deploy import WorkflowDeployTool
        from yigthinker.tools.workflow.workflow_manage import WorkflowManageTool
        registry.register(WorkflowGenerateTool(workflow_registry))
        registry.register(WorkflowDeployTool(workflow_registry))
        registry.register(WorkflowManageTool(workflow_registry))

    return registry
```

### Layer 2: Workflow Registry (Shared state, file-based)

The `WorkflowRegistry` is a new module that reads/writes JSON files at `~/.yigthinker/workflows/`. It is NOT session-scoped (unlike `VarRegistry`). It is process-scoped: one instance shared by all three workflow tools within a single Yigthinker process.

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `WorkflowRegistry` | CRUD for workflow metadata, version management, run history updates | Filesystem (`~/.yigthinker/workflows/`), read by tools and health check hook |

**Critical design decision:** The registry is file-based JSON, not a database. This aligns with Yigthinker's design principle of self-contained, no-infrastructure-required operation. The registry uses `filelock` (already a dependency) for concurrent access safety when Gateway serves multiple sessions.

```python
class WorkflowRegistry:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.home() / ".yigthinker" / "workflows")
        self._index_path = self._base_dir / "registry.json"

    def load_index(self) -> dict:
        """Read registry.json. Returns empty structure if not found."""

    def save_index(self, data: dict) -> None:
        """Write registry.json with filelock for concurrent access."""

    def get_manifest(self, name: str) -> dict | None:
        """Read manifest.json for a specific workflow."""

    def save_manifest(self, name: str, manifest: dict) -> None:
        """Write manifest.json for a specific workflow."""

    def next_version(self, name: str) -> str:
        """Determine next version string (v1, v2, ...)."""

    def update_run_status(self, name: str, status: str, ...) -> None:
        """Update last_run, failure counts. Called by /api/rpa/report."""

    def list_active(self) -> list[dict]:
        """Return all workflows with status='active'."""
```

**Concurrency model:** The registry uses `filelock` around writes. Reads are unprotected (acceptable because JSON files are small and writes are atomic via write-to-temp-then-rename). This matches the pattern used by `AutoDream._do_dream()` which already uses `filelock` for the same reason.

### Layer 3: Behavior Layer (System prompt injection)

The "automate everything" directive is injected into the system prompt. The existing code in `agent.py` constructs the system prompt from:
1. Memory content via `ctx.context_manager.build_memory_section(loaded)` (line 103-104)
2. Subagent notifications (lines 108-114)

The behavior directive and health alerts follow the same pattern.

**Two injection paths:**

1. **Static directive** (constant text, set once at build time): Stored on `AgentLoop._workflow_directive`, set by `agent.set_workflow_directive()` in `builder.py`. Prepended to system prompt on every LLM call.

2. **Dynamic health alerts** (per-session, set by SessionStart hook): Written to `ctx.system_inject` by the health check hook. Read by `AgentLoop.run()` alongside memory content.

**Integration point in `agent.py` (around lines 101-114):**

```python
# After memory and subagent notification assembly:

# Static workflow behavior directive
if self._workflow_directive:
    system_prompt = (self._workflow_directive + "\n\n" + (system_prompt or "")).strip() or None

# Dynamic hook-injected content (workflow health alerts)
if ctx.system_inject:
    system_prompt = ((system_prompt or "") + "\n\n" + ctx.system_inject).strip() or None
```

### Layer 4: SessionStart Health Check Hook

A new hook registered on `SessionStart` that reads the `WorkflowRegistry` and injects alerts into `ctx.system_inject`.

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `workflow_health_check` hook | Read registry, identify failing/overdue workflows, inject alerts | `WorkflowRegistry` (read), `SessionContext.system_inject` (write via HookEvent.ctx) |

**Registration in `builder.py` (follows existing `dream_hook` pattern at lines 122-133):**

```python
if workflow_reg is not None:
    from yigthinker.hooks.workflow_health import make_workflow_health_hook
    health_hook = make_workflow_health_hook(workflow_reg)
    hook_registry.register("SessionStart", "*", health_hook)
```

**SharedWorkflowRegistry creation and flow through `builder.py`:**

```python
# In build_app():
workflow_reg = None
if gate("workflow", settings=settings):
    from yigthinker.tools.workflow.registry import WorkflowRegistry
    workflow_reg = WorkflowRegistry()

tools = build_tool_registry(pool=pool, workflow_registry=workflow_reg)
```

The `WorkflowRegistry` is created once in `build_app()` and passed to both `build_tool_registry()` (for tools) and `make_workflow_health_hook()` (for the hook). This single instance serves all sessions.

### Layer 5: Gateway RPA Endpoints

Two new HTTP POST endpoints mounted on the existing FastAPI app. No WebSocket involvement -- these are plain REST endpoints called by external Python scripts.

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `POST /api/rpa/callback` | Receive failure callbacks, create/reuse session, run AgentLoop for diagnosis | `AgentLoop`, `SessionRegistry`, `WorkflowRegistry`, aiosqlite dedup store |
| `POST /api/rpa/report` | Receive execution status reports, update registry | `WorkflowRegistry` only (no LLM) |

**Authentication:** Both endpoints use the same `GatewayAuth` bearer token verification as existing endpoints. Generated scripts include the gateway token in their `config.yaml`.

**Mount pattern in `server.py` `_mount_routes()`:**

```python
@app.post("/api/rpa/callback")
async def rpa_callback(request: Request):
    token = _extract_token(request)
    if not self._auth.verify(token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from yigthinker.gateway.rpa_callback import handle_rpa_callback
    return await handle_rpa_callback(request, self)

@app.post("/api/rpa/report")
async def rpa_report(request: Request):
    token = _extract_token(request)
    if not self._auth.verify(token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from yigthinker.gateway.rpa_report import handle_rpa_report
    return await handle_rpa_report(request, self._workflow_registry)
```

**`/api/rpa/callback` execution flow:**

1. Parse `RPACallbackRequest` from request body
2. Deduplicate via `callback_id` (use aiosqlite, same pattern as Teams/Feishu event dedup)
3. Load workflow manifest from `WorkflowRegistry` for context
4. Create or reuse session via `GatewayServer.handle_message()` with a diagnostic prompt
5. Parse LLM response into structured `RPACallbackResponse` (fix_applied/skip/escalate)
6. Return JSON response to the calling script

**`/api/rpa/report` execution flow:**

1. Parse `RPAReportRequest` from request body
2. Call `WorkflowRegistry.update_run_status()` directly
3. Return 200 OK -- no LLM, no session, no cost

**Gateway dependency from generated scripts:** Scripts treat Gateway as optional. `POST /api/rpa/callback` with `timeout=30`. If `ConnectionError`, return `{"action": "escalate"}`. Gateway offline = lose self-healing, not execution.

### Layer 6: MCP Servers (Independent packages)

Two independent Python packages, each implementing an MCP server with 5 tools. They communicate with Yigthinker via stdio protocol, identical to how any MCP server is loaded by `MCPLoader`.

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `yigthinker-mcp-powerautomate` | 5 tools for PA Flow management via PA Management API | Power Automate API (`api.flow.microsoft.com`), Azure Management API (for Azure Function deployment) |
| `yigthinker-mcp-uipath` | 5 tools for UiPath Orchestrator management via OData API | UiPath Orchestrator API |

**Independence guarantee:** These packages have zero import dependencies on the `yigthinker` package. They are standalone MCP servers that happen to be useful with Yigthinker. Any MCP-compatible client can use them.

**Yigthinker integration:** Users add entries to `.mcp.json`. The existing `MCPLoader` in `build_app()` discovers and loads them automatically. The tools appear in the flat `ToolRegistry` alongside native tools. The LLM sees `pa_deploy_flow`, `ui_deploy_process`, etc. as regular tools.

**Build order implication:** MCP servers are completely independent of all other v1.1 work. They can be built first, last, or in parallel. They are not blockers for any other component.

---

## Data Flow

### Workflow Generation Flow

```
User request --> AgentLoop --> LLM decides to call workflow_generate
  --> WorkflowGenerateTool.execute()
    --> Read DataFrame schemas from ctx.vars (column names, dtypes)
    --> Resolve Jinja2 template based on target (python/power_automate/uipath)
    --> Render template with step definitions, schemas, checkpoint config
    --> Write files to ~/.yigthinker/workflows/{name}/v{n}/
      |-- main.py
      |-- config.yaml
      |-- requirements.txt
      |-- checkpoint_utils.py
    --> Update WorkflowRegistry (registry.json + manifest.json)
    --> Return ToolResult with generation summary
  --> LLM sees result, may proceed to workflow_deploy
```

### Workflow Deployment Flow (auto mode)

```
LLM calls workflow_deploy(mode="auto", target="uipath")
  --> WorkflowDeployTool.execute()
    --> Read manifest from WorkflowRegistry
    --> Check mode:
      local: Generate task_scheduler.xml or crontab entry, done
      guided: Generate setup guide + paste-ready artifacts, done
      auto: Prepare package, return instructions for LLM to call MCP tools
    --> Update registry with deploy status
    --> Return ToolResult
```

**Critical architecture question: Can a tool call another tool?**

In the current architecture, tools do NOT call other tools directly. The `AgentLoop` is the sole orchestrator of tool calls. Tools return `ToolResult` to the LLM, and the LLM decides the next tool call. This means `workflow_deploy` in `auto` mode cannot directly invoke `ui_deploy_process`.

**Recommended pattern:** `workflow_deploy` in `auto` mode returns a ToolResult containing structured next-step instructions:

```json
{
  "status": "deploy_ready",
  "next_steps": [
    {"tool": "ui_deploy_process", "params": {"package_path": "...", "process_name": "..."}},
    {"tool": "ui_manage_trigger", "params": {"process_id": "...", "schedule": "0 8 5 * *"}}
  ],
  "message": "Package ready. Please deploy using the tools listed in next_steps."
}
```

The LLM then calls the MCP tools through the normal AgentLoop cycle. This keeps the architecture clean: tools don't have hidden side-channel calls to other tools.

### RPA Callback Flow (Self-Healing)

```
Generated script runs --> checkpoint fails after retry
  --> POST /api/rpa/callback with error details
    --> Gateway authenticates (bearer token)
    --> Deduplicates callback_id (aiosqlite)
    --> Loads workflow manifest from WorkflowRegistry
    --> Creates/reuses session
    --> Constructs diagnostic prompt with error context + manifest
    --> Runs AgentLoop.run() with diagnostic prompt
    --> LLM analyzes error, decides action (fix_applied/skip/escalate)
    --> Returns structured RPACallbackResponse
  --> Script receives response
    --> fix_applied: retries with modified params
    --> skip: continues without that step
    --> escalate: notifies human, raises
```

### RPA Report Flow (Status Update)

```
Generated script completes --> POST /api/rpa/report
  --> Gateway authenticates
  --> WorkflowRegistry.update_run_status()
  --> Returns 200 OK
  --> (No LLM involved, no session created)
```

### SessionStart Health Check Flow

```
Any new conversation starts --> AgentLoop.run() fires SessionStart hook
  --> workflow_health_check hook runs
    --> WorkflowRegistry.load_index()
    --> Check each active workflow:
      - failure_count_30d / run_count_30d > 0.3? --> alert
      - schedule says should have run but last_run is old? --> alert
    --> If alerts: event.ctx.system_inject = "[Workflow Alerts] ..."
  --> Hook returns HookResult.ALLOW
  --> AgentLoop continues, ctx.system_inject included in system prompt
  --> LLM sees alerts, can proactively inform user
```

---

## Patterns to Follow

### Pattern 1: Tool with Injected Dependency

**What:** Tools that need access to a shared resource receive it via `__init__`, not by reaching into global state.

**When:** `WorkflowGenerateTool`, `WorkflowDeployTool`, `WorkflowManageTool` all need `WorkflowRegistry`.

**Existing precedent:** `SqlQueryTool(pool=pool)` in `registry_factory.py` line 49.

```python
class WorkflowGenerateTool:
    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry
```

### Pattern 2: Hook as Closure Capturing Dependencies

**What:** Hooks that need access to shared state are closures returned by factory functions.

**When:** `workflow_health_check` hook needs `WorkflowRegistry`.

**Existing precedent:** `dream_hook` in `builder.py` lines 122-133 captures `auto_dream`, `memory_manager`, and `provider`.

```python
def make_workflow_health_hook(registry: WorkflowRegistry):
    async def workflow_health_check(event: HookEvent) -> HookResult:
        index = registry.load_index()
        alerts = []
        for name, wf in index.get("workflows", {}).items():
            if wf.get("status") != "active":
                continue
            run_count = max(wf.get("run_count_30d", 1), 1)
            if wf.get("failure_count_30d", 0) / run_count > 0.3:
                alerts.append(f"{name}: high failure rate in last 30 days")
        if alerts and event.ctx is not None:
            event.ctx.system_inject = f"[Workflow Alerts] {'; '.join(alerts)}"
        return HookResult.ALLOW
    return workflow_health_check
```

### Pattern 3: Gateway Route Delegation to Module

**What:** Keep `server.py` thin. Route handlers delegate to dedicated modules.

**When:** `/api/rpa/callback` and `/api/rpa/report`.

**Existing precedent:** Channel adapters register their own routes (e.g., `TeamsAdapter` mounts its webhook). Dashboard entry endpoints delegate simple logic inline. For more complex logic (session management), separate modules handle it.

### Pattern 4: Feature Gate for New Capabilities

**What:** New subsystems are gated behind `gates.py` feature flags, matching the memory/dream pattern.

**When:** Workflow tools, health check hook, behavior directive.

**Existing precedent:** `gate("session_memory", settings=settings)` and `gate("auto_dream", settings=settings)` in `builder.py` lines 108, 119.

```python
if gate("workflow", settings=settings):
    workflow_reg = WorkflowRegistry()
    # register tools, hooks, etc.
```

### Pattern 5: Optional Dependency Guard for Tool Registration

**What:** Tools with optional dependencies use try/except import guards.

**When:** Workflow tools depend on Jinja2 (optional `workflow` extras group).

**Existing precedent:** `_register_forecast_tools()` in `registry_factory.py` lines 31-41 wraps forecast tool imports in `try/except ModuleNotFoundError`.

```python
def _register_workflow_tools(registry: ToolRegistry, workflow_reg: WorkflowRegistry) -> None:
    try:
        from yigthinker.tools.workflow.workflow_generate import WorkflowGenerateTool
        from yigthinker.tools.workflow.workflow_deploy import WorkflowDeployTool
        from yigthinker.tools.workflow.workflow_manage import WorkflowManageTool
    except ModuleNotFoundError:
        return  # Jinja2 not installed
    registry.register(WorkflowGenerateTool(workflow_reg))
    registry.register(WorkflowDeployTool(workflow_reg))
    registry.register(WorkflowManageTool(workflow_reg))
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Tools Calling Other Tools Directly

**What:** Having `workflow_deploy` directly invoke MCP tools like `ui_deploy_process` by reaching into the `ToolRegistry` and calling `execute()`.

**Why bad:** Bypasses the AgentLoop's hook/permission pipeline. `PreToolUse` hooks would not fire. Permission checks would not run. The tool call would not appear in message history. The LLM would not see the result.

**Instead:** Return a structured result that tells the LLM what to do next. The LLM then calls the MCP tools through the normal AgentLoop cycle.

### Anti-Pattern 2: Adding a WorkflowManager Layer Between Tools and Registry

**What:** Creating an intermediate "manager" class that sits between the tools and the `WorkflowRegistry`, adding abstraction without value.

**Why bad:** Yigthinker's architecture is deliberately flat. The tools directly access the registry. Adding a manager layer creates indirection that makes the code harder to follow and contradicts the "flat tools" principle.

**Instead:** Each tool calls `self._registry.method()` directly.

### Anti-Pattern 3: Storing Workflow State in SessionContext

**What:** Putting workflow registry data into `ctx.vars` or a session-scoped field.

**Why bad:** Workflows outlive sessions. A workflow created in session A must be visible in session B. Workflow metadata is user-scoped (per user home directory), not session-scoped.

**Instead:** The `WorkflowRegistry` reads/writes to `~/.yigthinker/workflows/`, which persists across all sessions.

### Anti-Pattern 4: Making MCP Servers Import Yigthinker

**What:** Having `yigthinker-mcp-powerautomate` import types or utilities from the `yigthinker` package.

**Why bad:** MCP servers must be independently installable and usable. Any MCP-compatible client should be able to use them. Coupling to Yigthinker defeats the MCP architecture.

**Instead:** MCP servers are fully self-contained packages with their own types, auth, and API client code.

### Anti-Pattern 5: Complex System Prompt Modification via Monkey-Patching

**What:** Having the behavior layer modify the system prompt by intercepting or wrapping the provider call, or by monkey-patching `ContextManager.build_memory_section()`.

**Why bad:** The system prompt path is already clean: `agent.py` builds it from memory + notifications. Adding another injection point should follow the same pattern.

**Instead:** Use `AgentLoop._workflow_directive` for static text and `ctx.system_inject` for dynamic hook content. Both are read at the same point where memory and notifications are assembled.

---

## HookEvent Context Access: Required Modification

**Current `HookEvent` does not carry `SessionContext`.** The dataclass (in `types.py` lines 57-72) has `session_id`, `transcript_path`, `tool_name`, etc. -- but no `ctx` reference.

The health check hook needs to write `event.ctx.system_inject`. Two options:

**Option A (Recommended):** Add `ctx: SessionContext | None = None` to `HookEvent`. The `AgentLoop.run()` already constructs `HookEvent` for `SessionStart` (lines 76-80) and can pass `ctx` there. Forward-compatible -- future hooks may need ctx access.

**Option B:** Have the hook return alert text via `HookResult.message`, and have `AgentLoop` special-case `SessionStart` results to inject the message into system prompt. This avoids modifying `HookEvent` but adds conditional logic to the loop.

**Recommendation:** Option A. Minimal change (one optional field), clean data flow.

```python
# In types.py:
@dataclass
class HookEvent:
    # ... existing fields ...
    ctx: "SessionContext | None" = None  # Set for SessionStart/SessionEnd events

# In agent.py AgentLoop.run(), line 76-80:
start_event = HookEvent(
    event_type="SessionStart",
    session_id=ctx.session_id,
    transcript_path=ctx.transcript_path,
    ctx=ctx,  # NEW: pass ctx for hook access
)
```

---

## Specific Modifications to Existing Files

### 1. `yigthinker/types.py` -- Add ctx field to HookEvent

Add one field to HookEvent dataclass. Requires forward reference since SessionContext is in `session.py`.

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from yigthinker.session import SessionContext

@dataclass
class HookEvent:
    # ... existing 11 fields ...
    ctx: "SessionContext | None" = None
```

### 2. `yigthinker/session.py` -- Add system_inject field

Add one field to SessionContext dataclass.

```python
@dataclass
class SessionContext:
    # ... existing 12 fields (lines 80-91) ...
    system_inject: str = ""  # Hook-injected system prompt content
```

### 3. `yigthinker/agent.py` -- Read directive + system_inject, set_workflow_directive(), pass ctx to SessionStart hook

Three changes:
- Add `_workflow_directive` field and `set_workflow_directive()` method
- Pass `ctx=ctx` to SessionStart HookEvent construction
- Read `self._workflow_directive` and `ctx.system_inject` when building system prompt

### 4. `yigthinker/registry_factory.py` -- Add workflow_registry parameter, register 3 tools

Change `build_tool_registry()` signature to accept optional `workflow_registry`. Add conditional registration block.

### 5. `yigthinker/builder.py` -- Create WorkflowRegistry, pass to tools, register hook, set directive

Add ~15 lines after the memory/dream setup block to conditionally create `WorkflowRegistry`, register the health check hook, and set the behavior directive.

### 6. `yigthinker/gateway/server.py` -- Mount 2 RPA routes, store registry reference

Add `self._workflow_registry` field. Mount two `@app.post` routes in `_mount_routes()` with lazy imports to handler modules. The `WorkflowRegistry` reference needs to be available to `rpa_report` handler. Since routes are mounted in `__init__` but registry is created in `start()`, the registry is stored on `self` during `start()`.

### 7. `pyproject.toml` -- Add workflow extras group

```toml
workflow = ["jinja2>=3.1"]
```

---

## Suggested Build Order

The dependency chain dictates build order.

### Phase 1: Foundation (no dependencies on other new components)

**1a. WorkflowRegistry** (`yigthinker/tools/workflow/registry.py`)
- Zero dependencies on other new code
- Pure file I/O + JSON + filelock
- Must be built first: tools, hooks, and gateway endpoints all depend on it
- Test: unit tests for create/read/update, version management, concurrent access

**1b. Jinja2 Templates** (`yigthinker/tools/workflow/templates/`)
- Zero dependencies on other new code
- Static template files
- Test: render templates with sample data, verify output scripts are syntactically valid

### Phase 2: Native Tools (depends on Phase 1)

**2a. workflow_generate** -- depends on WorkflowRegistry + templates
**2b. workflow_manage** -- depends on WorkflowRegistry only
**2c. workflow_deploy** -- depends on WorkflowRegistry + workflow_generate output

Modify `registry_factory.py` to register all three.

### Phase 3: Integration Wiring (depends on Phase 2)

**3a.** Add `system_inject` to SessionContext, `ctx` to HookEvent (small type changes)
**3b.** Behavior directive constant + `AgentLoop.set_workflow_directive()` + `AgentLoop.run()` reads
**3c.** SessionStart health check hook (`make_workflow_health_hook`)
**3d.** Feature gate wiring in `builder.py`

### Phase 4: Gateway Endpoints (depends on Phase 1 + Phase 3)

**4a.** `/api/rpa/report` -- simpler, pure registry write
**4b.** `/api/rpa/callback` -- complex, creates session + runs AgentLoop

### Phase 5: MCP Servers (independent, parallel with any phase)

**5a.** `yigthinker-mcp-powerautomate` -- 5 tools, MSAL auth
**5b.** `yigthinker-mcp-uipath` -- 5 tools, OAuth2 auth

### Phase 6: End-to-End Integration Testing

Full integration: generate -> deploy (guided) -> manage -> health check -> callback -> report

**Why this order:**
1. Registry first because everything reads/writes it
2. Tools second because they are the core user-facing capability
3. Wiring third because it connects tools to the agent behavior layer
4. Gateway fourth because it enables external script callbacks
5. MCP servers anytime because they are completely independent
6. E2E last because it requires all components working together

---

## Scalability Considerations

| Concern | At 1 user | At 10 concurrent sessions | At 100 workflows |
|---------|-----------|---------------------------|-------------------|
| Registry file I/O | No concern | filelock serializes writes; reads fast (small JSON) | registry.json may grow; consider index partitioning later |
| Template rendering | Instant (<100ms) | Independent per session, no contention | Templates are stateless |
| /api/rpa/callback | One AgentLoop run per callback | Each callback gets own session; serialized by session key lock | Concurrent callbacks to different workflows process in parallel |
| /api/rpa/report | Pure write | filelock handles concurrent writes | Consider batch reporting if volume exceeds 1000/day |
| MCP server processes | One per server type | Shared across all sessions (loaded once at startup) | N/A |

---

## Sources

- Existing codebase: `yigthinker/agent.py` (lines 62-219), `yigthinker/builder.py` (lines 23-135), `yigthinker/registry_factory.py` (lines 1-83), `yigthinker/gateway/server.py` (lines 1-508), `yigthinker/hooks/executor.py`, `yigthinker/hooks/registry.py`, `yigthinker/session.py` (lines 78-96), `yigthinker/types.py` (lines 56-72), `yigthinker/tools/base.py`, `yigthinker/tools/registry.py`, `yigthinker/mcp/loader.py`, `yigthinker/mcp/client.py`, `yigthinker/context_manager.py`, `yigthinker/gates.py`, `yigthinker/memory/auto_dream.py`, `yigthinker/gateway/auth.py`, `yigthinker/gateway/session_registry.py`
- Design spec: `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md`
- [Jinja2 on PyPI](https://pypi.org/project/Jinja2/) -- template engine for code generation
- [PyPowerAutomate](https://pypi.org/project/PyPowerAutomate/) -- Python Power Automate flow management
- [UiPath Python SDK](https://pypi.org/project/uipath/) -- official UiPath Python SDK
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) -- official MCP server/client SDK
- [MCP Best Practices](https://modelcontextprotocol.info/docs/best-practices/) -- architecture and implementation guide
