# yigthinker-mcp-powerautomate

MCP server exposing Power Automate Flow Management tools to Yigthinker
(and any other MCP-compatible LLM agent). Deploy notification flows,
trigger runs, inspect run history, toggle flow state, and list
connections -- all over MCP stdio transport.

- **Package:** `yigthinker-mcp-powerautomate`
- **Module:** `yigthinker_mcp_powerautomate`
- **Command:** `python -m yigthinker_mcp_powerautomate`
- **Requires:** Python 3.11+, an Azure AD app registration with Power
  Automate API permissions.

This package is an independent pip-installable wheel that plugs into
Yigthinker via the standard Model Context Protocol (MCP) stdio transport.
Yigthinker itself never imports this package at runtime -- it is spawned
as a subprocess by `yigthinker/mcp/loader.py` and dispatched to exclusively
through MCP `tools/call` messages (the architect-not-executor invariant).

---

## Prerequisites

Before installing the package, register an Azure AD application that the
MCP server will use for authentication.

1. **Register an app** in Azure Portal:
   Navigate to **Azure Portal > App registrations > New registration**.
   Give it a name (e.g. `yigthinker-powerautomate`) and register.

2. **Add API permissions** for Power Platform:
   Go to **API permissions > Add a permission > APIs my organization uses**,
   search for **Power Automate** (or "Microsoft Flow Service"), and add
   these **Application** permissions:

   - `PowerAutomate.Flows.Read`  -- read flow definitions and run history
   - `PowerAutomate.Flows.Write` -- create, update, enable/disable flows

   These two permissions are the minimum needed for all 5 tools.

3. **Grant admin consent:**
   On the same API permissions page, click **Grant admin consent for
   [your tenant]**. Without admin consent, all MSAL token requests will
   fail with `AADSTS65001` -- see Troubleshooting.

4. **Create a client secret:**
   Go to **Certificates & secrets > New client secret**. Copy the secret
   value immediately -- Azure will not show it again.

5. **Record your credentials:**
   - **Tenant ID** -- from Azure Portal > App registrations > your app >
     Overview > "Directory (tenant) ID"
   - **Client ID** -- from the same Overview page > "Application (client) ID"
   - **Client secret** -- the value you copied in step 4

---

## Installation

### Local dev (monorepo, recommended during 0.x)

From the Yigthinker repo root:

```bash
# 1. Install core Yigthinker test/runtime deps
pip install -e .[test]

# 2. Install this package editable
pip install -e packages/yigthinker-mcp-powerautomate[test]
```

Verify the install:

```bash
python -c "import yigthinker_mcp_powerautomate; print(yigthinker_mcp_powerautomate.__file__)"
python -m yigthinker_mcp_powerautomate  # Ctrl-C to stop; fails with env error if config missing
```

### GitHub source install (before PyPI)

Until PyPI publication lands, the single-command non-editable install path is:

```bash
uv tool install "yigthinker[rpa-pa] @ git+https://github.com/Henghenggao/Yigthinker.git"
```

### From PyPI (future)

Once both packages are published:

```bash
pip install yigthinker[rpa-pa]
```

The `rpa-pa` optional extra on core Yigthinker declares a dependency on
this package, so a single install pulls both. Until then, use the two-step
editable path above.

---

## Configuration

### Environment variables

The server reads these on startup via `PowerAutomateConfig.from_env`
(`yigthinker_mcp_powerautomate/config.py`). Three are required and three
are optional with sensible defaults:

| Variable                     | Required | Default                                                   | Description                          |
|------------------------------|----------|-----------------------------------------------------------|--------------------------------------|
| `POWERAUTOMATE_TENANT_ID`    | Yes      | --                                                        | Azure AD tenant ID                   |
| `POWERAUTOMATE_CLIENT_ID`    | Yes      | --                                                        | AAD app registration client ID       |
| `POWERAUTOMATE_CLIENT_SECRET`| Yes      | --                                                        | AAD app client secret                |
| `POWERAUTOMATE_SCOPE`        | No       | `https://service.flow.microsoft.com//.default`            | OAuth2 scope (see note below)        |
| `POWERAUTOMATE_BASE_URL`     | No       | `https://api.flow.microsoft.com`                          | Flow Management API base URL         |
| `POWERAUTOMATE_AUTHORITY`    | No       | `https://login.microsoftonline.com/{tenant_id}`           | MSAL authority URL                   |

If any of the three required variables are missing, the server exits at
startup with a `RuntimeError` listing every missing variable name.

**Scope note:** The default scope `https://service.flow.microsoft.com//.default`
contains a **double slash** (`//`). This is NOT a typo -- it is the correct
scope string for the Power Automate Flow Service API. Do NOT remove the
extra slash. See Troubleshooting for details.

### .mcp.json with vault:// secrets

Yigthinker resolves `vault://` env references via the project loader
(`yigthinker/mcp/loader.py`). The transform is:

```text
vault://powerautomate_client_id  ->  VAULT_POWERAUTOMATE_CLIENT_ID
vault://powerautomate_tenant_id  ->  VAULT_POWERAUTOMATE_TENANT_ID
vault://powerautomate_scope      ->  VAULT_POWERAUTOMATE_SCOPE
```

i.e. `vault://` is stripped, the remainder is uppercased, and the final
upper-cased name must resolve to an environment variable set on the host
where Yigthinker runs. The loader then re-injects that value under the
original key name into the MCP subprocess environment (so
`vault://powerautomate_client_id` ends up as `POWERAUTOMATE_CLIENT_ID`
inside the spawned `python -m yigthinker_mcp_powerautomate` process).

**Keys MUST be flat underscore-separated.** Slash paths
(`vault://powerautomate/client_id`) are silently broken because they
produce invalid env var names like `VAULT_POWERAUTOMATE/CLIENT_ID`. Use
`vault://powerautomate_client_id`, NOT `vault://powerautomate/client_id`.

Add this block to your project's `.mcp.json` (either at the repo root
or `~/.yigthinker/.mcp.json`). The three required env vars use `vault://`
references; optional vars can be omitted to use defaults:

```json
{
  "mcpServers": {
    "powerautomate": {
      "command": "python",
      "args": ["-m", "yigthinker_mcp_powerautomate"],
      "env": {
        "POWERAUTOMATE_TENANT_ID":     "vault://powerautomate_tenant_id",
        "POWERAUTOMATE_CLIENT_ID":     "vault://powerautomate_client_id",
        "POWERAUTOMATE_CLIENT_SECRET": "vault://powerautomate_client_secret"
      }
    }
  }
}
```

If you also want to override the optional settings via vault, expand the
`env` block:

```json
"env": {
    "POWERAUTOMATE_TENANT_ID":     "vault://powerautomate_tenant_id",
    "POWERAUTOMATE_CLIENT_ID":     "vault://powerautomate_client_id",
    "POWERAUTOMATE_CLIENT_SECRET": "vault://powerautomate_client_secret",
    "POWERAUTOMATE_BASE_URL":      "vault://powerautomate_base_url",
    "POWERAUTOMATE_SCOPE":         "vault://powerautomate_scope",
    "POWERAUTOMATE_AUTHORITY":     "vault://powerautomate_authority"
}
```

Then set the actual values on the host shell before launching Yigthinker:

```bash
export VAULT_POWERAUTOMATE_TENANT_ID='your-tenant-id'
export VAULT_POWERAUTOMATE_CLIENT_ID='your-client-id'
export VAULT_POWERAUTOMATE_CLIENT_SECRET='your-client-secret'
yigthinker
```

On Windows PowerShell, use `$env:VAULT_POWERAUTOMATE_CLIENT_ID = 'value'`
instead of `export`.

---

## Tools

The server exposes 5 MCP tools. Each returns a JSON-stringified dict as
a single `TextContent` block -- the Yigthinker agent sees the stringified
JSON and parses it downstream. On failure each tool returns
`{"error": "<code>", ...}` dicts rather than raising, so the MCP stdio
transport never sees a broken frame.

All tools that operate on a specific environment take `environment_id` as
a **required** field. Power Automate tenants may have multiple environments
(Dev, Test, Prod) -- the `environment_id` disambiguates which environment
to target on every call.

### `pa_deploy_flow`

Deploy a notification-only HTTP Trigger to Send Email (V2) flow. Creates the
flow in the specified environment and returns the flow ID and HTTP trigger
URL. The trigger URL is the callback to paste into `config.yaml` for
Phase 9 guided mode.

| Field              | Type         | Default                          | Description                                         |
|--------------------|--------------|----------------------------------|-----------------------------------------------------|
| `flow_name`        | `str`        | (required)                       | Logical name for the flow                           |
| `environment_id`   | `str`        | (required)                       | Power Automate environment to deploy into           |
| `recipients`       | `list[str]`  | (required)                       | Email addresses to receive notifications            |
| `subject_template` | `str`        | `"{workflow_name} notification"` | Email subject; `{workflow_name}` replaced at runtime |
| `display_name`     | `str | None` | `None` (defaults to `flow_name`) | Optional display name for the flow                  |

Example input:

```json
{
  "flow_name": "monthly_ar_aging_notify",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "recipients": ["finance-team@example.com"],
  "subject_template": "{workflow_name} completed"
}
```

Returns:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "http_trigger_url": "https://prod-XX.westus.logic.azure.com/...",
  "flow_name": "monthly_ar_aging_notify",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

On failure returns `{"error": "http_error", "tool": "pa_deploy_flow", "status": 400, "detail": "..."}`.

### `pa_trigger_flow`

Manually invoke a flow run via its HTTP trigger. Sends a POST to the
flow's trigger URL with an optional JSON payload and returns the run
status.

| Field           | Type             | Default    | Description                                    |
|-----------------|------------------|------------|------------------------------------------------|
| `flow_id`       | `str`            | (required) | The flow identifier to trigger                 |
| `environment_id`| `str`            | (required) | Power Automate environment ID                  |
| `trigger_input` | `dict[str, Any]` | `{}`       | Optional JSON payload passed to the trigger    |

Example input:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "trigger_input": {"report_date": "2026-04-30"}
}
```

Returns:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "run_id": "08585...",
  "status": "Running",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### `pa_flow_status`

Query the most recent run history for a flow. Returns a list of run
summaries with status, start time, and end time.

| Field           | Type  | Default    | Description                              |
|-----------------|-------|------------|------------------------------------------|
| `flow_id`       | `str` | (required) | The flow identifier to query runs for    |
| `environment_id`| `str` | (required) | Power Automate environment ID            |
| `top`           | `int` | `10`       | Maximum number of recent runs to return  |

Example input:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "top": 5
}
```

Returns:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "runs": [
    {
      "run_id": "08585...",
      "status": "Succeeded",
      "start_time": "2026-04-12T08:00:00Z",
      "end_time": "2026-04-12T08:00:05Z"
    }
  ]
}
```

### `pa_pause_flow`

Disable or enable a flow. Posts to the flow's disable/enable endpoint
to toggle its running state.

| Field           | Type                            | Default    | Description                                          |
|-----------------|---------------------------------|------------|------------------------------------------------------|
| `flow_id`       | `str`                           | (required) | The flow identifier to modify                        |
| `environment_id`| `str`                           | (required) | Power Automate environment ID                        |
| `action`        | `"disable"` or `"enable"`       | (required) | `"disable"` to pause the flow, `"enable"` to resume  |

Example input:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "action": "disable"
}
```

Returns:

```json
{
  "flow_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "action": "disable",
  "result": "success"
}
```

### `pa_list_connections`

List available connections in a Power Automate environment, optionally
filtered by connector name.

| Field            | Type         | Default    | Description                                              |
|------------------|--------------|------------|----------------------------------------------------------|
| `environment_id` | `str`        | (required) | Power Automate environment ID                            |
| `connector_name` | `str | None` | `None`     | Optional connector filter (e.g. `"shared_office365"`)    |

Example input:

```json
{
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "connector_name": "shared_office365"
}
```

Returns:

```json
{
  "environment_id": "Default-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "connections": [
    {
      "connection_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "display_name": "Office 365 Outlook",
      "connector": "/providers/Microsoft.PowerApps/apis/shared_office365",
      "statuses": [{"status": "Connected"}]
    }
  ]
}
```

---

## End-to-end example

Once the server is configured and the package is installed:

```bash
yigthinker --query "Deploy a notification flow called 'monthly_ar_notify' to my default environment, sending to finance-team@example.com when the workflow completes."
```

The Yigthinker agent will:

1. Call `pa_deploy_flow(flow_name="monthly_ar_notify", environment_id="Default-...", recipients=["finance-team@example.com"])`
   -- creates the notification flow and returns the flow ID + HTTP trigger URL.
2. Return the `http_trigger_url` which the user (or the LLM) pastes into
   `config.yaml` as the `pa_notify_url` for Phase 9 guided mode.

Yigthinker's own `workflow_deploy target=power_automate deploy_mode=auto` tool
detects this package via `importlib.util.find_spec("yigthinker_mcp_powerautomate")`
and returns instructional `next_steps` pointing at `pa_deploy_flow`, so the
LLM can chain the deploy in a single turn.

---

## Troubleshooting

### "MCP package not detected by workflow_deploy auto mode"

Symptom: `workflow_deploy target=power_automate deploy_mode=auto` returns
an error saying the MCP package is missing.

Run this to verify installation:

```bash
python -c "import importlib.util; print(importlib.util.find_spec('yigthinker_mcp_powerautomate'))"
```

If it prints `None`, the package is not installed in Yigthinker's Python
environment. Reinstall with:

```bash
uv tool install "yigthinker[rpa-pa] @ git+https://github.com/Henghenggao/Yigthinker.git"
# or from the monorepo:
pip install -e packages/yigthinker-mcp-powerautomate[test]
```

Make sure the `yigthinker` CLI and `python` point to the same virtual
environment (`which yigthinker` and `which python` on Linux/macOS, or
`where.exe yigthinker` and `where.exe python` on Windows).

### "MSAL 401 AADSTS65001 -- admin consent required"

Symptom: Token acquisition fails with error code `AADSTS65001`:
"The user or administrator has not consented to use the application."

Fix: Navigate to **Azure Portal > App registrations > your app > API
permissions** and click **Grant admin consent for [your tenant]**. The
app must have `PowerAutomate.Flows.Read` and `PowerAutomate.Flows.Write`
permissions granted with admin consent before MSAL can acquire a token.

### "MSAL 401 AADSTS700016 -- application not found"

Symptom: Token acquisition fails with error code `AADSTS700016`:
"Application with identifier was not found in the directory."

Fix: Verify that `POWERAUTOMATE_CLIENT_ID` matches the **Application
(client) ID** on your app registration's Overview page exactly. Common
causes:

- Copy-paste error (extra whitespace or truncated UUID)
- Using the Object ID instead of the Application (client) ID
- Wrong tenant -- the app must be registered in the tenant identified by
  `POWERAUTOMATE_TENANT_ID`

### "stdio handshake hangs"

Symptom: Yigthinker reports the MCP server spawn failed, or the agent
hangs after being asked to use a `pa_*` tool.

Run the server manually to see startup errors:

```bash
POWERAUTOMATE_TENANT_ID=test POWERAUTOMATE_CLIENT_ID=test \
POWERAUTOMATE_CLIENT_SECRET=test \
python -m yigthinker_mcp_powerautomate
```

It should wait on stdin for a JSON-RPC message -- Ctrl-C to stop. If it
exits immediately, check stderr for a `RuntimeError` from
`PowerAutomateConfig.from_env` listing missing env vars. On Windows
PowerShell, set the vars first:

```powershell
$env:POWERAUTOMATE_TENANT_ID = 'test'
$env:POWERAUTOMATE_CLIENT_ID = 'test'
$env:POWERAUTOMATE_CLIENT_SECRET = 'test'
python -m yigthinker_mcp_powerautomate
```

Other causes:
- **Server logging to stdout instead of stderr.** The MCP stdio protocol
  uses stdout exclusively for JSON-RPC frames -- any non-protocol print
  to stdout breaks the handshake. If you added print statements to the
  package, remove them or use `print(..., file=sys.stderr)`.
- **Async runtime clash.** If you are embedding the server inside another
  async loop, import and call `build_server(config)` directly instead of
  invoking `python -m yigthinker_mcp_powerautomate`.

### "The double-slash in the scope URL looks wrong"

The default OAuth2 scope is:

```text
https://service.flow.microsoft.com//.default
```

The double slash (`//`) between `microsoft.com` and `.default` is
**correct**. This is the documented scope format for the Power Automate
Flow Service API. Do NOT remove the extra slash -- doing so will cause
MSAL token acquisition to fail with an `invalid_scope` or silent 401
error.

If you have overridden `POWERAUTOMATE_SCOPE`, make sure your custom
value preserves the double slash. The `api.flow.microsoft.com` base URL
(used for REST calls) does NOT have a double slash -- only the
`service.flow.microsoft.com` scope string does.

---

## Development

```bash
git clone https://github.com/FinCode-Dev/Yigthinker.git
cd Yigthinker/packages/yigthinker-mcp-powerautomate
pip install -e .[test]
pytest tests/ -x
```

Run the full package test suite:

```bash
pytest tests/ -v --tb=short
```

Tests use `respx` for HTTP mocking and `unittest.mock.patch` for MSAL
mocking. No real Azure AD or Power Automate tenant is needed.

---

## License

Same as Yigthinker -- see the repository root `LICENSE` file.

## Links

- [Yigthinker main repo](https://github.com/FinCode-Dev/Yigthinker)
- [Power Automate Management API](https://learn.microsoft.com/en-us/rest/api/power-automate/)
- [Register an AAD app for Power Automate](https://learn.microsoft.com/en-us/power-automate/dev/register-app)
- [MSAL Python ConfidentialClientApplication](https://learn.microsoft.com/en-us/python/api/msal/msal.application.confidentialclientapplication)
- [Model Context Protocol specification](https://spec.modelcontextprotocol.io/)
