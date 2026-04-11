# yigthinker-mcp-uipath

MCP server exposing UiPath Automation Cloud Orchestrator as 5 tools for
Yigthinker (and any other MCP-compatible LLM agent). Ship Python workflows
to UiPath as Cross-Platform `.nupkg` packages, trigger jobs, inspect job
history, manage scheduled triggers, and check queue status -- all over MCP
stdio transport.

- **Package:** `yigthinker-mcp-uipath`
- **Module:** `yigthinker_mcp_uipath`
- **Command:** `python -m yigthinker_mcp_uipath`
- **Requires:** Python 3.11+, UiPath Automation Cloud tenant with an
  External Application (confidential client) configured for OAuth2.

This package is an independent pip-installable wheel that plugs into
Yigthinker via the standard Model Context Protocol (MCP) stdio transport.
Yigthinker itself never imports this package at runtime -- it is spawned
as a subprocess by `yigthinker/mcp/loader.py` and dispatched to exclusively
through MCP `tools/call` messages (the architect-not-executor invariant).

---

## Installation

### Local dev (monorepo, recommended during 0.x)

From the Yigthinker repo root:

```bash
# 1. Install core Yigthinker with the rpa-uipath extra metadata
pip install -e .[rpa-uipath]

# 2. Install this package editable (the extra above declares the dep,
#    but hatchling does not support local path-based resolution yet)
pip install -e packages/yigthinker-mcp-uipath[test]
```

Verify the install:

```bash
python -c "import yigthinker_mcp_uipath; print(yigthinker_mcp_uipath.__file__)"
python -m yigthinker_mcp_uipath  # Ctrl-C to stop; fails with env error if config missing
```

### From PyPI (future)

Once both packages are published:

```bash
pip install yigthinker[rpa-uipath]
```

The `rpa-uipath` optional extra on core Yigthinker declares a dependency on
this package, so a single install pulls both. Until then, use the two-step
editable path above.

---

## Configuration

### UiPath Automation Cloud setup

1. Log into the [UiPath Automation Cloud](https://cloud.uipath.com).
2. Under **Admin -> External Applications**, create a **Confidential
   Application** with these Orchestrator API scopes:

   - `OR.Execution`     -- start jobs, read job state
   - `OR.Jobs`          -- job history queries
   - `OR.Folders.Read`  -- resolve folder paths to ids
   - `OR.Queues`        -- queue status queries
   - `OR.Monitoring`    -- alternative for certain queue endpoints

   These 5 scopes are the minimum needed for all 5 tools. Enterprise
   tenants under least-privilege review may need to request `OR.Default`
   instead -- see Troubleshooting.

3. Record the **App ID** (client id) and **App Secret** (client secret).
4. Record your **Organization name** (also called "account logical name"
   -- it's the first path segment of your Automation Cloud URL) and
   **Tenant name** (the second path segment, typically `DefaultTenant`).
5. Note your tenant's Orchestrator base URL. It has the shape:

   ```text
   https://cloud.uipath.com/<organization>/<tenantName>/orchestrator_
   ```

   Trailing `orchestrator_` is **required** -- it's the API path prefix,
   not the tenant name. Without the trailing underscore every request
   gets routed to the wrong endpoint.

### Environment variables

The server reads these on startup via `UipathConfig.from_env`
(`yigthinker_mcp_uipath/config.py`). All six are read -- five are
required and one is optional with a default:

| Variable               | Required | Example                                                          |
|------------------------|----------|------------------------------------------------------------------|
| `UIPATH_CLIENT_ID`     | Yes      | `abc123...` (External App "App Id")                              |
| `UIPATH_CLIENT_SECRET` | Yes      | `s3cr3t...` (External App "App Secret")                          |
| `UIPATH_BASE_URL`      | Yes      | `https://cloud.uipath.com/ACMECorp/DefaultTenant/orchestrator_`  |
| `UIPATH_TENANT`        | Yes      | `DefaultTenant`                                                  |
| `UIPATH_ORGANIZATION`  | Yes      | `ACMECorp`                                                       |
| `UIPATH_SCOPE`         | No       | `OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring`   |

The variable is **`UIPATH_SCOPE`** -- singular, no trailing `S`. If
omitted, the server defaults to the 5-scope string above.

Scopes are **space-separated** per RFC 6749 -- never comma-separated.
Passing `OR.Execution,OR.Jobs` will be rejected by the UiPath token
endpoint with a 401 `invalid_scope` error.

If `UIPATH_TENANT` or `UIPATH_ORGANIZATION` is missing, the server exits
at startup with a `RuntimeError` listing every missing variable. These
two fields are read separately from `UIPATH_BASE_URL` because the OAuth2
token endpoint path and the per-request tenant headers need them
individually -- the base URL is parsed for the request origin, not
decomposed into tenant / organization segments.

### .mcp.json with vault:// secrets

Yigthinker resolves `vault://` env references via the project loader
(`yigthinker/mcp/loader.py`). The transform is:

```text
vault://uipath_client_id  ->  VAULT_UIPATH_CLIENT_ID
vault://uipath_tenant     ->  VAULT_UIPATH_TENANT
vault://uipath_scope      ->  VAULT_UIPATH_SCOPE      (singular!)
```

i.e. `vault://` is stripped, the remainder is uppercased, and the final
upper-cased name must resolve to an environment variable set on the host
where Yigthinker runs. The loader then re-injects that value under the
original key name into the MCP subprocess environment (so
`vault://uipath_client_id` ends up as `UIPATH_CLIENT_ID` inside the
spawned `python -m yigthinker_mcp_uipath` process).

**Keys MUST be flat underscore-separated.** Slash paths
(`vault://uipath/client_id`) are silently broken because they produce
invalid env var names like `VAULT_UIPATH/CLIENT_ID`. Use
`vault://uipath_client_id`, NOT `vault://uipath/client_id`.

Add this block to your project's `.mcp.json` (either at the repo root
or `~/.yigthinker/.mcp.json`). All 6 env vars are included -- secrets
via `vault://`, public values (base URL, tenant, org name, scope string)
can be inline if you prefer to keep the vault surface small:

```json
{
  "mcpServers": {
    "uipath": {
      "command": "python",
      "args": ["-m", "yigthinker_mcp_uipath"],
      "env": {
        "UIPATH_CLIENT_ID":     "vault://uipath_client_id",
        "UIPATH_CLIENT_SECRET": "vault://uipath_client_secret",
        "UIPATH_BASE_URL":      "https://cloud.uipath.com/ACMECorp/DefaultTenant/orchestrator_",
        "UIPATH_TENANT":        "DefaultTenant",
        "UIPATH_ORGANIZATION":  "ACMECorp",
        "UIPATH_SCOPE":         "OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring"
      }
    }
  }
}
```

If you prefer to keep tenant / organization / scope out of version
control, swap them to vault too:

```json
"UIPATH_TENANT":       "vault://uipath_tenant",
"UIPATH_ORGANIZATION": "vault://uipath_organization",
"UIPATH_SCOPE":        "vault://uipath_scope"
```

Then set the actual values on the host shell before launching
Yigthinker:

```bash
export VAULT_UIPATH_CLIENT_ID='your-actual-client-id'
export VAULT_UIPATH_CLIENT_SECRET='your-actual-secret'
# Only if you chose vault:// for these:
export VAULT_UIPATH_TENANT='DefaultTenant'
export VAULT_UIPATH_ORGANIZATION='ACMECorp'
export VAULT_UIPATH_SCOPE='OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring'
yigthinker
```

On Windows PowerShell, use `$env:VAULT_UIPATH_CLIENT_ID = 'value'`
instead of `export`.

---

## Tools

The server exposes 5 MCP tools. Each returns a JSON-stringified dict as
a single `TextContent` block -- the Yigthinker agent sees the stringified
JSON and parses it downstream. On failure each tool returns
`{"error": "<code>", ...}` dicts rather than raising, so the MCP stdio
transport never sees a broken frame.

### `ui_deploy_process`

Build a Cross-Platform Python `.nupkg` from a local script, upload it to
UiPath Orchestrator, and create a Release.

| Field             | Type | Default     |
|-------------------|------|-------------|
| `workflow_name`   | str  | (required)  |
| `script_path`     | str  | (required)  |
| `folder_path`     | str  | `"Shared"`  |
| `package_version` | str  | `"1.0.0"`   |

Example input:

```json
{
  "workflow_name": "monthly_ar_aging",
  "script_path": "/home/you/workflows/ar_aging.py",
  "folder_path": "Shared",
  "package_version": "1.0.0"
}
```

Returns `{"status": "deployed", "process_key": ..., "release_key": ...}`
on success, `{"error": "script_not_found" | "http_error", ...}` on
failure.

### `ui_trigger_job`

Start a job for an existing Release via OData `UiPath.Server.Jobs.StartJobs`.

| Field             | Type | Default     |
|-------------------|------|-------------|
| `process_key`     | str  | (required)  |
| `folder_path`     | str  | `"Shared"`  |
| `input_arguments` | dict | `{}`        |

Example input:

```json
{
  "process_key": "monthly_ar_aging",
  "folder_path": "Shared",
  "input_arguments": {"as_of_date": "2026-04-30"}
}
```

`input_arguments` is serialized to a JSON STRING inside the `startInfo`
body per the UiPath OData contract -- never a nested object. Returns
`{"job_id": ..., "state": ...}`.

### `ui_job_history`

List recent jobs for a process.

| Field         | Type | Default     |
|---------------|------|-------------|
| `process_key` | str  | (required)  |
| `folder_path` | str  | `"Shared"`  |
| `top`         | int  | `10` (1-100)|

Example input:

```json
{
  "process_key": "monthly_ar_aging",
  "folder_path": "Shared",
  "top": 5
}
```

Returns `{"process_key": ..., "count": N, "jobs": [...]}`. Returns an
empty `jobs: []` list rather than an error when no release has been
created yet for the process.

### `ui_manage_trigger`

CRUD operations on scheduled triggers (UiPath `ProcessSchedules`).

| Field          | Type                                               | Default     |
|----------------|----------------------------------------------------|-------------|
| `process_key`  | str                                                | (required)  |
| `action`       | `"create"` / `"pause"` / `"resume"` / `"delete"`   | (required)  |
| `folder_path`  | str                                                | `"Shared"`  |
| `cron`         | str                                                | `None`      |
| `trigger_name` | str                                                | `None`      |

Example input (create a monthly trigger):

```json
{
  "process_key": "monthly_ar_aging",
  "action": "create",
  "trigger_name": "monthly-5th-8am",
  "cron": "0 8 5 * *"
}
```

`cron` is required for `action="create"`. `trigger_name` is required for
all four actions. Cross-field validation fires BEFORE any HTTP call, so
bad input short-circuits with zero network traffic.

### `ui_queue_status`

Return item counts per state for a queue.

| Field         | Type | Default     |
|---------------|------|-------------|
| `queue_name`  | str  | (required)  |
| `folder_path` | str  | `"Shared"`  |

Example input:

```json
{
  "queue_name": "InvoiceIntake",
  "folder_path": "Shared"
}
```

Returns `{"queue_name": ..., "new": N, "in_progress": N, "failed": N, "successful": N}`
via the modern OData path
`/odata/QueueItems/UiPath.Server.Configuration.OData.GetQueueItemsByStatusCount`.

---

## End-to-end example

Once the server is configured and the package is installed:

```bash
yigthinker --query "Deploy my monthly AR aging workflow (written at ~/workflows/ar_aging.py) to UiPath as 'monthly_ar_aging' version 1.0.0, then show me the last 5 job runs."
```

The Yigthinker agent will:

1. Call `ui_deploy_process(workflow_name="monthly_ar_aging", script_path="/home/you/workflows/ar_aging.py")`
   -- builds the `.nupkg`, uploads it, creates a Release, returns the
   release key.
2. Call `ui_trigger_job(process_key="monthly_ar_aging")` if you asked
   for an immediate run (skip if you only asked to deploy).
3. Call `ui_job_history(process_key="monthly_ar_aging", top=5)` to show
   the last 5 runs.

Yigthinker's own `workflow_deploy target=uipath deploy_mode=auto` tool
also detects this package via `importlib.util.find_spec("yigthinker_mcp_uipath")`
and returns instructional `next_steps` pointing at `ui_deploy_process`,
so the LLM can chain the deploy in a single turn.

---

## Troubleshooting

### "yigthinker_mcp_uipath MCP package is not detected"

Symptom: `workflow_deploy target=uipath deploy_mode=auto` returns an
error saying the MCP package is missing, even though you ran
`pip install -e packages/yigthinker-mcp-uipath[test]`.

Causes and fixes:

- **Wrong Python environment.** The `yigthinker` CLI must run in the
  same venv where you installed the package. Run `which yigthinker`
  (`where.exe yigthinker` on Windows) and `which python` to confirm
  they point at the same `.venv`.
- **Phase 9 drift regression.** Run:

  ```bash
  python -m pytest tests/test_tools/test_mcp_detection.py -x -v
  ```

  If that fails, `yigthinker/tools/workflow/mcp_detection.py` was
  edited to reference a legacy module name instead of the canonical
  `yigthinker_mcp_uipath`. The Phase 11 drift guard should have
  caught it -- rerun the test to find the offending line.

- **Import failure at package level.** Try:

  ```bash
  python -c "import importlib.util; print(importlib.util.find_spec('yigthinker_mcp_uipath'))"
  ```

  It should print a `ModuleSpec`, not `None`. If it prints `None`,
  reinstall with `pip install -e packages/yigthinker-mcp-uipath[test]`.

### Server exits at startup with "missing required env vars"

Symptom: `python -m yigthinker_mcp_uipath` exits immediately with a
`RuntimeError` naming `UIPATH_TENANT` or `UIPATH_ORGANIZATION`.

Cause: `UipathConfig.from_env` requires **five** vars (not three):
`UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET`, `UIPATH_BASE_URL`,
`UIPATH_TENANT`, `UIPATH_ORGANIZATION`. If any are missing, the server
exits before the MCP stdio handshake. Earlier README drafts listed only
three required vars -- if you copied one of those, update your
`.mcp.json` to include all five.

Fix: Add `UIPATH_TENANT` and `UIPATH_ORGANIZATION` to your `.mcp.json`
env block (see Configuration above). `UIPATH_SCOPE` remains optional.

### OAuth2 returns 401 "invalid_client" or "invalid_scope"

Symptom: First tool call fails with an `http_error` containing
`status: 401`.

Causes and fixes:

- **Client id or secret wrong.** Double-check the `VAULT_UIPATH_CLIENT_ID`
  and `VAULT_UIPATH_CLIENT_SECRET` env vars are actually set in the
  parent shell before launching Yigthinker. Run
  `env | grep VAULT_UIPATH` (or `Get-ChildItem env:VAULT_UIPATH*` on
  PowerShell). If the grep comes back empty, `_resolve_env` will
  silently pass the literal string `vault://uipath_client_id` through
  to the subprocess, and UiPath's token endpoint rejects it.
- **Scopes rejected by tenant policy.** Some enterprise tenants reject
  granular `OR.*` scopes and require `OR.Default`. Try:

  ```bash
  export UIPATH_SCOPE="OR.Default"
  ```

  Note: `UIPATH_SCOPE` singular, and still space-separated if you pass
  multiple -- never commas, per RFC 6749. A comma-separated scope
  string is the single most common cause of a 401 `invalid_scope`.
- **Wrong tenant URL.** `UIPATH_BASE_URL` must end in `orchestrator_`
  (trailing underscore). Without it, the API path prefix is wrong and
  both OAuth2 and per-tool requests 404.
- **`UIPATH_TENANT` / `UIPATH_ORGANIZATION` mismatch.** These must match
  the segments in `UIPATH_BASE_URL`. For a base URL of
  `https://cloud.uipath.com/ACMECorp/DefaultTenant/orchestrator_`,
  `UIPATH_ORGANIZATION=ACMECorp` and `UIPATH_TENANT=DefaultTenant`. A
  mismatch frequently surfaces as a 401 `invalid_client` even though
  the credentials are correct, because UiPath's token endpoint is
  tenant-scoped.

### "MCP stdio handshake failed" or server hangs at startup

Symptom: Yigthinker reports the MCP server spawn failed, or the agent
hangs after being asked to use a `ui_*` tool.

Causes and fixes:

- **Server logging to stdout instead of stderr.** The MCP stdio
  protocol uses stdout exclusively for JSON-RPC frames -- any
  non-protocol print to stdout breaks the handshake. This server
  redirects all logging to stderr. If you added print statements to
  the package, remove them or use `print(..., file=sys.stderr)`.
- **Missing env vars cause `RuntimeError` at startup.** If any of
  `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET`, `UIPATH_BASE_URL`,
  `UIPATH_TENANT`, `UIPATH_ORGANIZATION` are unset,
  `UipathConfig.from_env` raises and the process exits `1` before
  the stdio handshake. Reproduce manually:

  ```bash
  UIPATH_CLIENT_ID=test UIPATH_CLIENT_SECRET=test \
  UIPATH_BASE_URL=https://cloud.uipath.com/ACMECorp/DefaultTenant/orchestrator_ \
  UIPATH_TENANT=DefaultTenant UIPATH_ORGANIZATION=ACMECorp \
  python -m yigthinker_mcp_uipath
  ```

  It should then wait on stdin for a JSON-RPC message -- Ctrl-C to
  stop. `UIPATH_SCOPE` is optional and will fall back to the default
  5-scope string. If the process exits instead of waiting, scroll up
  in stderr for the RuntimeError.
- **Async runtime clash.** This server uses `asyncio.run(run_stdio())`
  and the `mcp` SDK's built-in stdio transport. If you're embedding
  the server inside another async loop, import and call
  `build_server(config)` directly and drive it with your own
  transport instead of invoking `python -m yigthinker_mcp_uipath`.

---

## License

Same as Yigthinker -- see the repository root `LICENSE` file.

## Links

- [Yigthinker main repo](https://github.com/FinCode-Dev/Yigthinker)
- [UiPath External Applications docs](https://docs.uipath.com/automation-cloud/automation-cloud/latest/admin-guide/about-external-applications)
- [UiPath Orchestrator OData API reference](https://docs.uipath.com/orchestrator/reference)
- [UiPath Cross-Platform package format](https://docs.uipath.com/studio/standalone/latest/user-guide/about-cross-platform-projects)
- [Model Context Protocol specification](https://spec.modelcontextprotocol.io/)
