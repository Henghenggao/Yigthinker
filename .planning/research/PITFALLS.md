# Pitfalls Research: Workflow & RPA Bridge for Yigthinker

> **Status:** Pre-implementation research for v1.1. v1.1 shipped 2026-04-12. This document is a historical reference — consult shipped code and phase summaries for current state.

**Domain:** Adding workflow generation, RPA deployment, self-healing callbacks, and proactive AI suggestions to an existing Python agent system
**Researched:** 2026-04-09
**Confidence:** HIGH (codebase-informed) / MEDIUM (API reliability claims from WebSearch)

## Critical Pitfalls

### Pitfall 1: Jinja2 Template Injection in Generated Scripts

**What goes wrong:**
Templates for `main.py.j2`, `config.yaml.j2`, etc. render LLM-produced values (step names, SQL queries, column names, file paths) into executable Python code. If any of these values contain Jinja2 syntax (`{{ }}`, `{% %}`), the template engine evaluates them as expressions, enabling arbitrary code execution at generation time. This is Server-Side Template Injection (SSTI). CVE-2025-27516 (fixed in Jinja2 3.1.6) demonstrated that even Jinja2's sandbox can be bypassed via the `|attr` filter to reach `str.format` and escalate to RCE.

**Why it happens:**
The LLM produces step parameters containing user-supplied data (table names, column names, SQL fragments). These flow into `{{ step.params.query }}` slots in templates. Developers treat template rendering as "just string formatting" and forget that Jinja2 is a full expression evaluator. Unlike `df_transform`'s AST sandbox (which the codebase already handles correctly at `yigthinker/tools/dataframe/df_transform.py`), Jinja2 injection surfaces are less obvious because they exist at build time, not runtime.

**How to avoid:**
1. Use `jinja2.sandbox.SandboxedEnvironment` (not bare `Environment`) for ALL template rendering
2. Pin Jinja2 >= 3.1.6 in `pyproject.toml` to include the CVE-2025-27516 fix
3. Never pass raw LLM output as template source. Template files are static `.j2` files in the package; LLM output goes into the **context dict** only, never into the template string itself
4. Add an AST check on rendered output: after rendering `main.py.j2`, parse the output with `ast.parse()` and run a checker similar to `_SandboxChecker` from `df_transform.py` to reject scripts containing `__import__`, `exec()`, `eval()`, `os.system()`, or subprocess calls not explicitly whitelisted
5. Validate all step parameters against a strict schema before template rendering. Step `params` should be Pydantic-validated, not passed as raw dicts

**Warning signs:**
- Template files using `{{ step.params.* }}` without any input sanitization
- Test suite does not include a test with `{{ 7*7 }}` or `{{ config.__class__.__init__.__globals__ }}` as a step parameter value
- Jinja2 version constraint in pyproject.toml allows < 3.1.6

**Phase to address:**
Phase 1 (workflow_generate tool) -- template rendering is the very first thing built. Security must be baked in from day one, not bolted on later.

---

### Pitfall 2: Credential Leakage in Generated Scripts and Config Files

**What goes wrong:**
Generated `config.yaml` files are meant to use `vault://` placeholders, but the LLM (or the user via guided mode) substitutes real connection strings, API keys, or passwords. These scripts live in `~/.yigthinker/workflows/` as plain files. If the user commits them to version control, backs them up to cloud storage, or shares them for troubleshooting, credentials leak. The design spec's example `main.py` shows `client_credential=cfg["pa"]["client_secret"]` -- if `client_secret` is stored as plaintext in `config.yaml` instead of a vault reference, every copy of that script carries the credential.

**Why it happens:**
In "guided" deploy mode, the setup guide instructs users to "fill in your ERP connection string." Users paste `mssql+pyodbc://sa:P@ssw0rd!@server/db` directly into `config.yaml`. The system has no enforcement preventing plaintext credentials from being stored.

**How to avoid:**
1. Add a `CredentialValidator` that scans `config.yaml` after generation and on each read. Reject or warn on values matching known credential patterns (strings containing `://` with `@`, known API key formats like `sk-`, `Bearer `, hex strings > 32 chars adjacent to keys named `*_secret`, `*_key`, `*_password`, `*_token`)
2. Generated `config.yaml.j2` must emit `vault://` or `keyring://` references as defaults with inline comments explaining how to configure the credential backend
3. Auto-generate a `.gitignore` file in each workflow directory that excludes `config.yaml`
4. The `workflow_generate` tool result must explicitly warn: "config.yaml contains credential placeholders. Never commit this file to version control"
5. Support OS keyring (`keyring` library) as an alternative to HashiCorp Vault for SMB users. The codebase already mentions vault integration

**Warning signs:**
- `config.yaml` files in `~/.yigthinker/workflows/` containing plaintext passwords
- No `.gitignore` in workflow directories
- Users sharing workflow directories for troubleshooting with credentials exposed

**Phase to address:**
Phase 1 (workflow_generate) for generation-time protections, Phase 2 (workflow_deploy) for deploy-time credential validation.

---

### Pitfall 3: Registry File Corruption Under Concurrent Access

**What goes wrong:**
`~/.yigthinker/workflows/registry.json` is a single JSON file read and written by multiple actors: the `workflow_generate` tool (during script generation), `workflow_manage` tool (during lifecycle operations), the `/api/rpa/report` Gateway endpoint (receiving status reports from running scripts), and the `SessionStart` hook (registry health check). If two RPA scripts complete simultaneously and both POST to `/api/rpa/report`, the Gateway handles both requests concurrently (FastAPI is async), both read `registry.json`, both modify `last_run`, and one write overwrites the other. Partial writes produce truncated JSON that crashes all subsequent registry operations.

**Why it happens:**
The codebase already has `filelock` (used in `yigthinker/memory/auto_dream.py` for `.dream_lock`) but developers may forget to apply the same pattern to the registry because the Gateway is single-process and they assume async = sequential. It's not -- two concurrent HTTP requests to `/api/rpa/report` can interleave their file I/O operations.

**How to avoid:**
1. Use `filelock.FileLock` for ALL registry read-write operations, exactly as `auto_dream.py` does for `.dream_lock`
2. Implement atomic writes: write to `registry.json.tmp`, then `os.replace()` to `registry.json`. This prevents partial-write corruption even without locking
3. Wrap registry operations in a `RegistryManager` class with a single `async with registry.lock()` interface. Individual tools and endpoints must not do raw file I/O on `registry.json`
4. Write a backup before each update: copy current `registry.json` to `registry.json.bak` before writing. If `json.loads()` fails on read, fall back to `.bak`
5. On Windows, `os.replace()` is atomic within NTFS, but `filelock` is still needed for read-modify-write sequences

**Warning signs:**
- Registry operations using bare `open()` / `json.dump()` without locking
- No `.bak` file alongside `registry.json`
- Test suite lacks concurrent write tests for registry
- `json.JSONDecodeError` appearing in production logs

**Phase to address:**
Phase 1 (registry module) -- the `RegistryManager` with locking must be the first infrastructure built before any tool writes to it.

---

### Pitfall 4: Power Automate Management API Unreliability for Complex Flows

**What goes wrong:**
The PA Flow Definition creation API (`api.flow.microsoft.com`) is unreliable for complex flow creation. Microsoft has been migrating infrastructure (November 2025: HTTP trigger URLs changed from `logic.azure.com` to new URLs), breaking existing integrations. The API has connector-level throttling (600 calls per connection per 60 seconds), and flows that violate limits get throttled or disabled entirely after 14 days of continuous throttling. The `auto` deploy mode attempts to create/update Flows programmatically, but the API may silently produce malformed flows, return HTTP 429 throttling errors, or fail with opaque nested error messages. Additionally, the Power BI connector suffered a breaking change in October 2025 (Release Wave 2) where flows returning DAX query results stopped including data after a certain date.

**Why it happens:**
Power Automate's Management API was designed for the portal UI, not for external programmatic access. The API is a secondary citizen compared to the interactive editor. Microsoft's ongoing infrastructure migrations (URL changes, connector updates) create moving targets that break assumptions.

**How to avoid:**
1. The design spec already handles this correctly: `auto` mode for PA deploys compute via Azure Function and creates only simple notification Flows (HTTP Trigger -> Send Email). Enforce this strictly -- never attempt to create complex multi-step Flows via API
2. Implement aggressive retry with exponential backoff for PA API calls (start 1s, max 60s, add jitter). Handle HTTP 429 by reading the `Retry-After` header
3. Validate deployed flows by calling `pa_trigger_flow` with a test payload immediately after deployment. If the test fails, surface the error and fall back to `guided` mode automatically
4. Cache PA environment ID and connection references. Re-resolve them only when API calls fail with 401/403 (token expired) or 404 (resource moved)
5. In the MCP server, log the full API response body for every non-2xx response. PA error messages are often nested in `error.innererror.code` structures that are easy to miss

**Warning signs:**
- MCP server swallowing PA API errors and returning generic "deployment failed"
- No retry logic in PA API calls
- Tests mocking PA API responses without including 429/5xx scenarios
- Any hardcoded `logic.azure.com` URLs (these changed in Nov 2025)

**Phase to address:**
Phase 3 (MCP server packages) for the PA server implementation. The `guided` mode fallback must be solid in Phase 2 (workflow_deploy) so that PA API failures degrade gracefully.

---

### Pitfall 5: UiPath Authentication Model Fragmentation

**What goes wrong:**
UiPath Cloud and On-Premise have completely different authentication flows. Cloud uses OAuth2 client credentials via `https://account.uipath.com/oauth/token` with 24-hour token expiry plus refresh tokens. On-Premise uses a different endpoint (`https://{orchestrator-url}/api/Account/Authenticate`). Furthermore, UiPath deprecated API Keys in March 2025, migrating to Personal Access Tokens (PATs) and External Applications. PATs have expiration dates requiring periodic regeneration. Building the MCP server against one auth model and discovering the customer uses the other causes an auth layer rewrite.

**Why it happens:**
Developers test against UiPath Cloud (easier to set up for development), ship, then discover enterprise customers use On-Premise with completely different auth. Or they build against the deprecated API Key model from outdated documentation and discover it no longer works.

**How to avoid:**
1. Build UiPath MCP server auth as a strategy pattern from day one: `CloudAuth`, `OnPremAuth`, and `PATAuth` classes behind a single `UiPathAuth` interface. Selection based on environment variable: `UIPATH_AUTH_TYPE=cloud|onprem|pat`
2. Implement proactive token refresh: refresh when > 80% of the 24-hour validity has elapsed, not when the first 401 arrives. A 401 mid-operation can leave partial deployments in an inconsistent state
3. Document clearly in the MCP server README which env vars are needed for each auth type and what permissions/scopes the External Application requires
4. For PATs: implement expiry warnings. If the PAT expires within 7 days, log a warning on every MCP tool call. If expired, return a clear error with renewal instructions, not a generic 401

**Warning signs:**
- Single auth code path that only works with Cloud
- No token refresh logic (only initial token acquisition)
- Tests that hardcode access tokens instead of testing the refresh flow
- No `UIPATH_AUTH_TYPE` configuration option

**Phase to address:**
Phase 3 (MCP server packages) -- auth must be designed as multi-strategy before any UiPath tools are implemented.

---

### Pitfall 6: Self-Healing Callback Creates Unbounded LLM Cost

**What goes wrong:**
The `/api/rpa/callback` endpoint creates a session and runs the AgentLoop with error context. If a workflow has a systemic issue (database permanently moved, data source schema changed), every checkpoint failure triggers a callback, each callback incurs LLM cost, and the LLM cannot actually fix the problem. A workflow running hourly with 4 checkpoints could generate 96 LLM calls per day at $0.01-0.10 each. Multiply by 20 workflows and cost spirals to $20-200/day. Worse: the LLM may return `fix_applied` with incorrect parameters, causing the script to retry with bad data, succeed at the step level but produce garbage output.

**Why it happens:**
The self-healing pattern is designed for transient failures (network blip, credential rotation), but developers don't build protection against persistent/structural failures. The callback endpoint treats every error as potentially fixable without tracking failure history.

**How to avoid:**
1. Implement a circuit breaker: after 3 consecutive `fix_applied` or `skip` responses for the same workflow+checkpoint within 24 hours, auto-escalate instead of attempting more fixes. Store circuit breaker state in the workflow manifest
2. Add cost tracking per workflow. The callback endpoint must check `manifest.run_history` and refuse to create LLM sessions if the workflow has exceeded a configurable cost threshold (default: 10 LLM calls per workflow per day)
3. Rate-limit callbacks per workflow: max 1 callback per checkpoint per hour. Deduplicate via `callback_id` (already in the design spec) and add a time-based rate limit
4. The LLM system prompt for callback sessions must include: "If the error is structural (schema change, permanent URL change, missing table/database), return `escalate` immediately. Do not attempt to fix structural errors."
5. Log every callback decision and its associated cost in the registry manifest for visibility

**Warning signs:**
- No circuit breaker logic in the callback endpoint implementation
- No cost tracking or rate limiting on callbacks
- Test suite only tests happy path (single callback -> fix_applied -> success)
- LLM system prompt for callbacks doesn't distinguish transient from structural errors

**Phase to address:**
Phase 2 (Gateway endpoints) for the callback endpoint. Circuit breaker must be designed in from the start, not added after cost incidents.

---

### Pitfall 7: Generated Scripts Assume Python Environment Exists and Is Configured

**What goes wrong:**
Generated `main.py` scripts import `pandas`, `sqlalchemy`, `requests`, `msal`, and other libraries. The `requirements.txt` lists them, but the setup guide says "pip install -r requirements.txt" without specifying which Python, which venv, or handling PATH issues. On Windows, where Task Scheduler runs scripts as a service account, the Python path may not be in PATH, the venv may not be activated, and `pip` may install to the wrong Python installation. The script fails silently because Task Scheduler swallows stderr by default.

**Why it happens:**
Developers test on their own machine where Python is on PATH and the venv is active. Task Scheduler runs in a different user context with different environment variables. This is the #1 reported issue with Python + Task Scheduler integrations.

**How to avoid:**
1. Generated `task_scheduler.xml` must use absolute paths to `python.exe` (resolved at generation time from `sys.executable`), not just `python`
2. Generate a wrapper `run.bat` (Windows) or `run.sh` (Unix) that activates the venv and runs `main.py` with full error logging: `python.exe main.py >> run.log 2>&1`
3. The wrapper must set `PYTHONPATH` and activate the venv explicitly: call `.venv\Scripts\activate.bat && python main.py`
4. Include a `--preflight` flag in generated scripts that checks: Python version, all imports resolve, database connectivity, vault/keyring accessibility, Gateway reachability
5. Task Scheduler XML must set the `<WorkingDirectory>` to the workflow directory and redirect stdout/stderr to a log file

**Warning signs:**
- Generated `task_scheduler.xml` uses `python` instead of a fully qualified path
- No wrapper script generated alongside `main.py`
- No `--preflight` check available
- No error logging configured for scheduled execution

**Phase to address:**
Phase 1 (workflow_generate) for script structure and templates, Phase 2 (workflow_deploy local/guided) for Task Scheduler XML generation and wrapper scripts.

---

### Pitfall 8: Hook System Extension Breaks Existing Hook Ordering or Crashes Sessions

**What goes wrong:**
Adding a `SessionStart` hook for workflow health checks (`workflow_health.py`) inserts into the same `HookRegistry._hooks` list that existing hooks use. The `HookExecutor.run()` in `yigthinker/hooks/executor.py` processes hooks sequentially and returns on first BLOCK. If the workflow health check hook is registered before other `SessionStart` hooks and returns BLOCK (because the registry file is corrupted or missing), it blocks all session creation. If it raises an unhandled exception, the `HookExecutor` propagates it and crashes session creation. The current `HookExecutor.run()` has no exception handling around individual hook function calls.

**Why it happens:**
The current `HookRegistry` is a simple append-only list with no ordering guarantees. Registration order depends on import order in the builder. The `HookExecutor.run()` method does not wrap individual `hook_fn(event)` calls in try/except -- a single broken hook crashes the entire chain.

**How to avoid:**
1. The workflow health check hook must NEVER return BLOCK. It should only inject system context (alerts into session) and return ALLOW. Health check failures are informational, not blocking
2. Wrap the hook body in try/except: if the registry file is missing or corrupted, the hook must log a warning and return `HookResult.ALLOW`, not raise an exception
3. Add defensive exception handling to `HookExecutor.run()`: wrap each `await hook_fn(event)` in try/except. If a hook raises, log the error and continue to the next hook. This protects the system from any single broken hook
4. Consider adding an optional `priority` field to hook registration for ordering control (low priority for now -- not critical for v1.1, but prevents future issues)

**Warning signs:**
- Workflow health check hook returning `HookResult.BLOCK` for any reason
- No try/except in the health check hook body
- No try/except around `await hook_fn(event)` in `HookExecutor.run()`
- Test suite doesn't test session creation when `registry.json` is missing or corrupted

**Phase to address:**
Phase 2 (behavior layer and SessionStart hook). Must be implemented with defensive error handling from the start.

---

### Pitfall 9: MCP Server Process Crashes Silently Kill RPA Capabilities

**What goes wrong:**
MCP servers (`yigthinker-mcp-powerautomate`, `yigthinker-mcp-uipath`) run as child processes communicating via stdio. The current `MCPClient` (in `yigthinker/mcp/client.py`) has no crash detection or recovery. If the MCP server process dies (segfault, OOM, unhandled exception), `call_tool()` hangs or raises an opaque `BrokenPipeError`. The agent loop's generic `try/except Exception` catches this and returns `ToolResult(is_error=True)`, but the LLM may retry indefinitely. The MCP server stays dead for the rest of the session -- or in the Gateway's case, for the rest of the daemon's lifetime.

**Why it happens:**
The MCP spec defines a lifecycle (initialization -> operation -> shutdown) but the current `MCPClient` implementation has no health monitoring, no reconnection logic, and no process lifecycle management. `start()` has no timeout on `initialize()`. This is adequate for short-lived CLI sessions but dangerous for a long-running Gateway daemon that keeps MCP servers alive for hours or days.

**How to avoid:**
1. Add a `health_check()` method to `MCPClient` that sends a lightweight MCP operation (like `list_tools()` as a heartbeat) before critical tool calls. If it fails, attempt restart
2. Implement auto-restart: if `call_tool()` raises `BrokenPipeError`, `ConnectionError`, or `EOFError`, call `stop()` then `start()` automatically with max 3 restart attempts per hour
3. Add a startup timeout: if `start()` doesn't complete `initialize()` within 10 seconds, raise a clear error with the server name
4. In the Gateway daemon, run a background task that periodically checks MCP server health (every 60 seconds). If a server is dead, restart it or mark its tools as temporarily unavailable
5. The `workflow_deploy` tool (`auto` mode) must check MCP server health BEFORE attempting deployment. If the MCP server is down, fall back to `guided` mode with a clear message

**Warning signs:**
- No reconnection logic in `MCPClient`
- No timeout on `start()` or `call_tool()`
- Tests that only cover happy-path MCP interactions
- Gateway running for hours without any MCP health monitoring

**Phase to address:**
Phase 3 (MCP server packages) -- but `MCPClient` improvements (health check, auto-restart) should be done as infrastructure prep since existing MCP tools also benefit.

---

### Pitfall 10: LLM Provider Differences Break Workflow Tool Input Parsing

**What goes wrong:**
Workflow tools require the LLM to produce structured step definitions with complex nested inputs (`list[WorkflowStep]` with nested `params: dict`). Different providers handle tool calls differently: Claude produces well-structured JSON; GPT-4 sometimes produces malformed JSON or unexpected field values; Ollama local models may not follow nested tool schemas at all; Azure OpenAI may have subtly different response formats. The `workflow_generate` tool receives garbage step definitions from a weak model and renders broken scripts without catching the error at the input validation stage.

**Why it happens:**
The existing 26 tools work across all 4 providers because their inputs are simple (a SQL query string, a variable name, a code snippet). Workflow tools have the most complex input schemas in the entire tool set (`list[WorkflowStep]` with nested `params: dict`), which stress-tests provider schema adherence. The "all 4 providers must work" constraint meets tools that require structured reasoning.

**How to avoid:**
1. Validate `WorkflowGenerateInput` strictly with Pydantic BEFORE any template rendering. Reject step definitions with empty `action` fields, invalid `id` patterns, or circular `inputs` dependencies
2. Add a `_normalize_step_params()` function that coerces common LLM mistakes: string `"None"` -> `None`, stringified numbers -> `int`/`float`, missing required fields -> sensible defaults with warnings
3. For the behavior layer (proactive suggestions): keep suggestion logic in the system prompt, not in multi-step tool-call chaining. Weak models handle "respond with text suggesting automation" better than "call workflow_generate with these exact parameters"
4. Test workflow tools with all 4 providers. At minimum: Claude (structured), GPT-4 (mostly structured), and a local Ollama model (weak structured output)
5. Add a `--dry-run` option in `workflow_generate` that validates inputs and previews what would be generated without actually rendering templates

**Warning signs:**
- Workflow tools only tested with Claude
- No input normalization for LLM output quirks
- Proactive suggestion requires multi-step tool chaining that weak models cannot follow
- No validation step between LLM output and template rendering

**Phase to address:**
Phase 1 (workflow_generate) for input validation, Phase 2 (behavior layer) for provider-agnostic suggestion prompting.

---

### Pitfall 11: Gateway Callback Endpoint Missing Authentication

**What goes wrong:**
The `/api/rpa/callback` and `/api/rpa/report` endpoints accept POST requests from running scripts. If these endpoints don't require authentication, anyone on the network can: (a) trigger self-healing LLM sessions (cost attack), (b) inject fake status reports into the registry (data integrity attack), (c) craft callback payloads that cause the LLM to execute unintended actions. The design spec shows `callback_id` for idempotency but no authentication mechanism.

**Why it happens:**
The existing Gateway uses `GatewayAuth` (in `yigthinker/gateway/auth.py`) with a file-backed bearer token for HTTP/WS routes. But the RPA callback is a new endpoint pattern -- it's called by external scripts, not by TUI clients or channel adapters. Developers may skip auth because "it's just status reporting" or because they want to simplify the generated script's HTTP call.

**How to avoid:**
1. Require Bearer token auth on both `/api/rpa/callback` and `/api/rpa/report`, reusing the existing `GatewayAuth` mechanism. The same `_extract_token()` and `self._auth.verify(token)` pattern from `server.py`
2. Generated scripts must include the gateway token in `config.yaml` (as a `vault://` reference) and send it as `Authorization: Bearer {token}` on all callback/report requests
3. Additionally validate that `workflow_name` in the request exists in the registry. Reject callbacks for unknown workflows
4. Rate-limit the callback endpoint: max 10 requests per minute per IP to prevent abuse even with valid tokens

**Warning signs:**
- RPA endpoints mounted without auth middleware
- Generated scripts not including auth headers in callback/report HTTP calls
- No request validation beyond JSON parsing

**Phase to address:**
Phase 2 (Gateway endpoints) -- auth must be present from the first implementation.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Registry as single JSON file | Simple to implement, human-readable, easy to debug | Corruption risk under concurrency, no query capability, no indexing | Acceptable for v1.1 with filelock + atomic writes; migrate to SQLite if > 50 workflows |
| No workflow script signing | Skip code signing complexity | Users cannot verify script integrity after generation; tampering undetectable | Acceptable for v1.1; add HMAC-based checksums in manifest if enterprise customers need auditability |
| No generated script sandbox | Simpler scripts, full access to user's system | If a malicious or buggy script runs, it has full user permissions | Acceptable -- scripts are user-owned and generated by the user's own AI agent, not user-submitted code |
| Skipping UiPath On-Prem in v1.1 | Focus development effort on Cloud-first | On-prem enterprise customers blocked until auth strategy is added | Only if explicitly scoped out -- auth strategy pattern costs little and prevents rewrite |
| Inline checkpoint logic instead of separate library | Self-contained scripts with no pip dependency for checkpoint code | Code duplication across all generated scripts; updates require regenerating all scripts | Acceptable for v1.1 -- self-contained scripts are a design principle |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Power Automate API | Using deprecated `logic.azure.com` URLs that changed Nov 2025 | Use `api.flow.microsoft.com` base URL; resolve environment-specific URLs dynamically |
| Power Automate API | Attempting to create complex multi-step Flows via API | Only create simple Flows (HTTP Trigger -> single action) via API; use Azure Functions for compute |
| Power Automate API | Not handling nested error responses | Check `error.innererror.code` in addition to top-level status code; PA error nesting is 2-3 levels deep |
| UiPath Cloud API | Using deprecated API Keys (removed March 2025) | Use External Applications (OAuth2 client credentials) or Personal Access Tokens (PATs) |
| UiPath On-Prem | Using Cloud auth endpoint (`account.uipath.com`) for On-Prem | Detect auth type from env vars; On-Prem uses `/api/Account/Authenticate` on the Orchestrator URL |
| UiPath API | Not handling 24-hour token expiry | Proactively refresh token at 80% of TTL; implement transparent retry on 401 with re-auth |
| UiPath PATs | Not handling PAT expiration dates | Check PAT expiry on startup; warn if < 7 days remaining; clear error with renewal instructions if expired |
| Windows Task Scheduler | Using `python` instead of absolute path to `python.exe` | Resolve `sys.executable` at generation time; use full path in Task Scheduler XML `<Command>` |
| Windows Task Scheduler | Not setting `<WorkingDirectory>` | Set to workflow directory; all relative paths in scripts resolve from there |
| Windows Task Scheduler | Running as interactive user only | Configure "Run whether user is logged on or not" with service account for unattended execution |
| Gateway `/api/rpa/callback` | No authentication on callback endpoint | Require Bearer token auth; validate workflow_name exists in registry |
| Gateway `/api/rpa/report` | Blocking on Gateway unavailability in generated scripts | Use 5-second timeout on POST; swallow `ConnectionError` silently in generated scripts |
| Jinja2 templates | Using bare `Environment()` for template rendering | Always use `SandboxedEnvironment`; pin Jinja2 >= 3.1.6 for CVE-2025-27516 fix |
| MCP stdio lifecycle | Not handling MCP server process crashes | Add health_check + auto-restart in MCPClient; timeout on initialize() |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Registry health check reads full file on every SessionStart | Slow session creation as workflow count grows | Cache registry in memory with 60-second TTL; only read file on cache miss | > 20 workflows |
| Full manifest.json read for health check | I/O bound when manifests have long run histories | Health check reads only `registry.json` (index), not individual manifest files | > 100 runs per workflow (manifests grow unbounded) |
| Unbounded `run_history` in manifest.json | Manifest files grow to MB+ over months of daily execution | Cap `run_history` entries (keep last 100); archive older runs to `run_history.jsonl` | > 6 months of daily runs |
| MCP server process restart per session | High process creation overhead | Keep MCP servers alive for Gateway daemon lifetime; restart only on crash | Frequent workflow tool usage across sessions |
| LLM call per self-healing callback | $0.01-0.10 per callback adds up rapidly | Circuit breaker (3 attempts per checkpoint per 24h); cost cap per workflow per day | > 10 active workflows with any failure rate |
| Rendering large Jinja2 templates with many steps | Template rendering blocks event loop for complex workflows | Wrap template rendering in `asyncio.to_thread()` if > 10 steps | Workflows with > 20 steps |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Plaintext credentials in generated `config.yaml` | Credential exposure via git commit, file sharing, cloud backup | Credential pattern scanner on config writes; `vault://` as default; `.gitignore` in workflow dirs |
| No auth on `/api/rpa/callback` endpoint | Network attacker triggers unlimited LLM sessions (cost attack) | Require Bearer token auth (reuse `gateway.token`); validate `workflow_name` exists in registry |
| No auth on `/api/rpa/report` endpoint | Fake status reports pollute registry data integrity | Require Bearer token auth; validate `workflow_name` + `version` match registry entries |
| Rendered scripts containing dangerous imports | A compromised LLM response generates scripts with `subprocess`, `socket`, data exfiltration | Post-generation AST scan of rendered `main.py`; reject or warn on imports not in the template whitelist |
| LLM-generated `fix_applied` params injected into script kwargs | LLM could suggest params that alter SQL query to exfiltrate data | Whitelist allowed fix params per checkpoint in manifest; reject unknown params from callback response |
| MCP server env vars with vault refs resolved to plaintext at parent process level | Plaintext credentials visible in process environment | Resolve vault refs inside the MCP server process itself, not in the parent; use short-lived tokens |
| Task Scheduler XML with embedded user credentials | Windows stores credentials for "run whether user is logged on or not" | Use dedicated service account; document security implications clearly in setup guide |
| Generated scripts callable with arbitrary command-line args | An attacker could override config path to a malicious config | Generated scripts should use `argparse` with only whitelisted flags (`--test`, `--preflight`, `--config`) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Suggesting automation during exploratory analysis | User feels interrupted/pressured; declines and gets annoyed | Only suggest after task completion; never mid-analysis; require >= 3 distinct tool calls before suggesting |
| Re-suggesting after user declined | User feels the AI doesn't listen; trust erodes | Store declines in `suppressed_suggestions` with 3-month expiry (already in design spec); check before suggesting |
| Guided setup instructions too technical for finance managers | User abandons setup; automation never gets deployed | Provide two instruction levels: summary (for IM channels) and detailed (setup_guide.md); detect user role from channel |
| No feedback on scheduled workflow execution | User doesn't know if automation is working | Send proactive "ran successfully" notification for first 3 runs; then go silent; re-notify on failure |
| Workflow health alerts on every session start | Alert fatigue; user ignores important alerts after a week | Only alert if failure rate > 30% in 30d or execution is overdue by > 2x schedule interval; debounce repeated alerts |
| Deploy mode auto-selection without explanation | User confused about why "auto" vs "guided" was chosen | Always explain: "I'm using guided mode because no PA API access was detected. To use auto mode, configure..." |
| Error messages from PA/UiPath API exposed raw to user | Non-technical user sees `{"error":{"code":"ConnectionFailure","innererror":...}}` | Translate API errors to human-readable messages: "Could not connect to Power Automate. Check your API credentials." |

## "Looks Done But Isn't" Checklist

- [ ] **workflow_generate:** Template rendering uses `SandboxedEnvironment`, not bare `Environment` -- test with `{{ 7*7 }}` as a step param
- [ ] **workflow_generate:** Rendered `main.py` is validated with `ast.parse()` -- a template bug produces a syntax-invalid script
- [ ] **workflow_generate:** `config.yaml` emits only `vault://` or `keyring://` references, never plaintext credential values -- scan output
- [ ] **workflow_generate:** Generated scripts include `--preflight` flag -- run it on a clean machine to verify
- [ ] **workflow_deploy (guided):** Generated `task_scheduler.xml` uses absolute Python path -- inspect `<Command>` element
- [ ] **workflow_deploy (guided):** Setup guide mentions venv activation -- test on machine without Python on PATH
- [ ] **workflow_deploy (guided):** Wrapper `run.bat` generated alongside `main.py` -- verify it activates venv and logs stderr
- [ ] **workflow_deploy (auto):** PA/UiPath API failure automatically falls back to `guided` mode -- test with API credentials revoked
- [ ] **workflow_manage (health_check):** Handles missing/corrupted `registry.json` gracefully -- returns "no workflows" not an exception
- [ ] **workflow_manage (rollback):** Previous version files are intact and complete -- verify rollback produces a working script
- [ ] **Gateway /api/rpa/callback:** Requires auth token -- test with no auth header and verify 401
- [ ] **Gateway /api/rpa/callback:** Circuit breaker prevents runaway LLM costs -- test with 5 consecutive failures for same checkpoint
- [ ] **Gateway /api/rpa/report:** Updates registry with file lock -- test concurrent POST requests from multiple scripts
- [ ] **MCP PA server:** Works with both Azure Function deploy and simple Flow creation -- test both paths
- [ ] **MCP UiPath server:** Works with both Cloud and On-Prem auth -- test against both endpoint types
- [ ] **Behavior layer:** Proactive suggestions work with Ollama models -- test with weak local model
- [ ] **SessionStart hook:** Handles missing `~/.yigthinker/workflows/` directory without blocking session creation

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Jinja2 template injection in generated script | LOW | Delete generated script; fix template to use SandboxedEnvironment; add AST validation; re-generate |
| Credential leak in config.yaml | HIGH | Rotate ALL leaked credentials immediately; audit git history with `git log -p config.yaml`; add credential scanner; add `.gitignore` |
| Registry corruption | MEDIUM | Restore from `registry.json.bak`; if no backup, rebuild index from `manifest.json` files in each workflow subdirectory |
| PA API deployment failure | LOW | Fall back to `guided` mode; user deploys manually; `auto` mode is not the critical path |
| UiPath auth failure | MEDIUM | Regenerate PAT or External Application credentials; update env vars; restart MCP server |
| Runaway LLM costs from callbacks | MEDIUM | Disable `/api/rpa/callback` temporarily via settings; add circuit breaker; review and fix underlying workflow issues |
| MCP server crash | LOW | Auto-restart (once implemented); if persistent, check stderr logs; fall back to `guided` mode |
| Hook crash blocking sessions | HIGH | If in production: comment out hook registration and restart Gateway; then fix exception handling in `HookExecutor.run()` |
| Generated script fails on Task Scheduler | LOW | Run `main.py --preflight` to diagnose; fix paths and venv activation; re-import Task Scheduler XML |
| LLM produces invalid step definitions | LOW | Pydantic validation catches before rendering; return clear error to LLM with specific validation failures; LLM auto-corrects |
| Gateway offline during script execution | NONE | Scripts degrade gracefully: lose self-healing and reporting, retain full execution capability |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Jinja2 template injection | Phase 1 (workflow_generate) | Unit test: render with `{{ 7*7 }}` param; AST check on output; SandboxedEnvironment enforced |
| Credential leakage | Phase 1 (generate) + Phase 2 (deploy) | Scan generated config.yaml for credential patterns; `.gitignore` present in workflow dirs |
| Registry corruption | Phase 1 (registry module) | Concurrent write test with asyncio.gather; filelock usage verified; atomic write with os.replace() |
| PA API unreliability | Phase 3 (MCP PA server) | Retry logic with 429 handling; auto-fallback to guided; tests with mocked API failures |
| UiPath auth fragmentation | Phase 3 (MCP UiPath server) | Multi-strategy auth tests; token refresh tested; PAT expiry warning implemented |
| Unbounded LLM costs | Phase 2 (Gateway callback) | Circuit breaker with 3-attempt limit; cost tracking in manifest; rate limit verified |
| Python env assumptions | Phase 1 (templates) + Phase 2 (deploy) | Generated XML uses absolute path; wrapper script present; --preflight check works |
| Hook ordering/crash | Phase 2 (behavior layer) | Health check hook always returns ALLOW; try/except in hook body; test with missing registry |
| MCP server crashes | Phase 1 (MCPClient) + Phase 3 (servers) | Auto-restart on BrokenPipeError; health check before tool calls; startup timeout |
| Provider differences | Phase 1 (generate) + Phase 2 (behavior) | Test with Claude + Ollama; input normalization; Pydantic validation before rendering |
| Missing callback auth | Phase 2 (Gateway endpoints) | Unauthenticated POST returns 401; token validation reuses existing GatewayAuth |

## Sources

- [Power Automate platform limits and throttling](https://learn.microsoft.com/en-us/power-automate/guidance/coding-guidelines/understand-limits) -- throttling limits, 14-day disable policy
- [Power Automate API rate limits](https://manueltgomes.com/microsoft/power-platform/powerautomate/api-rate-limits-and-throttling-in-power-automate/) -- connector-level 600 calls/60s limit
- [Power Automate troubleshoot broken connections](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/connections/troubleshoot-broken-connections) -- Nov 2025 URL migration
- [Power Automate flow limits and config](https://learn.microsoft.com/en-us/power-automate/limits-and-config) -- flow definition limits, 500 action cap
- [UiPath API key deprecation and PAT migration](https://docs.uipath.com/overview/other/latest/overview/migrating-from-api-keys-to-personal-access-tokens) -- API keys removed March 2025
- [UiPath Cloud API consumption guide](https://docs.uipath.com/orchestrator/automation-cloud/latest/api-guide/consuming-cloud-api) -- 24-hour token expiry, refresh flow
- [UiPath On-Prem auth options](https://forum.uipath.com/t/api-authentication-options-with-on-prem-orchestrator/389403) -- different endpoint for on-prem
- [CVE-2025-27516: Jinja2 sandbox breakout via attr filter](https://github.com/advisories/GHSA-cpwx-vrp4-4pq7) -- fixed in Jinja2 3.1.6
- [Jinja2 SandboxedEnvironment documentation](https://jinja.palletsprojects.com/en/stable/sandbox/) -- correct sandbox usage and capabilities
- [MCP Lifecycle specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle) -- stdio shutdown protocol, initialization requirements
- [Windows Task Scheduler schtasks vulnerabilities](https://cymulate.com/blog/task-scheduler-new-vulnerabilities-for-schtasks-exe/) -- UAC bypass, task hiding risks
- [JSON file corruption in concurrent Python](https://github.com/confident-ai/deepeval/issues/2322) -- race condition examples, truncated JSON
- [Python secure coding guidelines](https://www.aptori.com/blog/python-security-cheat-sheet-for-developers) -- exec() risks, credential handling best practices
- [RPA common pitfalls](https://yellow.systems/blog/rpa-project-challenges) -- 50% dev time on bot maintenance, brittle selectors
- [UiPath Healing Agent](https://support-rpa.blogspot.com/2025/03/understanding-uipath-healing-agent.html) -- self-healing pattern precedent
- Codebase analysis: `yigthinker/tools/dataframe/df_transform.py` (existing sandbox pattern), `yigthinker/memory/auto_dream.py` (existing filelock pattern), `yigthinker/gateway/server.py` (existing auth pattern), `yigthinker/gateway/auth.py` (existing token pattern), `yigthinker/mcp/client.py` (current MCP lifecycle), `yigthinker/hooks/executor.py` (hook execution model), `yigthinker/permissions.py` (permission system), `yigthinker/gateway/session_registry.py` (concurrency model)

---
*Pitfalls research for: Workflow & RPA Bridge additions to Yigthinker*
*Researched: 2026-04-09*
