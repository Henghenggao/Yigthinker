# Stack Research: Workflow & RPA Bridge Additions

> **Status:** Pre-implementation research for v1.1. v1.1 shipped 2026-04-12. This document is a historical reference — consult shipped code and phase summaries for current state.

**Project:** Yigthinker v1.1 -- Workflow Generation, RPA Deployment, Self-Healing, Lifecycle Management
**Researched:** 2026-04-09
**Confidence:** HIGH (template/registry), MEDIUM (PA API), HIGH (UiPath API)

## Context

This research covers ONLY the new dependencies required for the v1.1 Workflow & RPA Bridge milestone. The existing stack (Python 3.11, FastAPI, Pydantic, httpx, msal, pandas, SQLAlchemy, aiosqlite, PyArrow, MCP SDK, etc.) is validated and not re-evaluated. Focus: Jinja2 for template rendering, PA/UiPath API integration patterns, Azure Functions deployment SDK, MCP server authoring, workflow registry storage, and cron parsing.

## Recommended Stack Additions

### Template Rendering (Yigthinker Core)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Jinja2 | >=3.1.6 | Render Python/PA/UiPath scripts from `.j2` templates | Standard Python template engine. Used by Flask, Ansible, Cookiecutter, dbt -- battle-tested for code generation. v3.1.6 (Mar 2025) includes a critical sandbox escape fix (CVE-2025-27516 via `|attr` filter bypass). Pin `>=3.1.6` specifically to ensure the security fix. Jinja2 already has async rendering support via `jinja2.Environment(enable_async=True)` and `SandboxedEnvironment` for untrusted input (not needed here since templates are developer-authored, not user-supplied). Depends on MarkupSafe (auto-installed). | HIGH |

**Why Jinja2 over alternatives:**
- **string.Template (stdlib):** No loops, no conditionals, no includes. Cannot render multi-file script packages.
- **Mako:** More powerful but less popular, different syntax. Jinja2 is the Python ecosystem default.
- **Cheetah3/Chameleon:** Niche. Jinja2 has 10x the community and documentation.
- **f-strings/str.format:** Not suitable for multi-line code templates with control flow.

**Template pattern for this project:**

```python
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("yigthinker/tools/workflow/templates"),
    autoescape=select_autoescape([]),  # No HTML escaping for Python code
    keep_trailing_newline=True,        # Preserve newlines in generated scripts
    trim_blocks=True,                  # Clean up whitespace around block tags
    lstrip_blocks=True,                # Strip leading whitespace before blocks
)
template = env.get_template("base/main.py.j2")
script = template.render(steps=steps, config=config, checkpoints=checkpoints)
```

Do NOT use `SandboxedEnvironment` -- templates are shipped with the codebase, not user-supplied. Sandboxing adds overhead and restricts template features unnecessarily.

### Cron Expression Parsing (Yigthinker Core)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| croniter | >=6.0.0 | Parse cron expressions for schedule validation and "should have run" checks | Used in the `SessionStart` hook to detect overdue workflow executions (comparing `schedule` + `last_run` against current time). Also used to render human-readable schedule descriptions in workflow metadata. v6.2.2 (Mar 2026) is current, requires Python >=3.9. Maintained by the Pallets ecosystem (Flask maintainers). Zero dependencies. | HIGH |

**Why croniter over alternatives:**
- **cronsim:** Smaller, but croniter has broader adoption (60M+ monthly downloads vs 1M for cronsim).
- **python-crontab:** System crontab manipulation tool, not a pure parser. Wrong scope.
- **Manual parsing:** Error-prone for edge cases (day-of-week vs day-of-month interaction, `L`, `W`, `#` modifiers).

**Usage pattern for health check hook:**

```python
from croniter import croniter
from datetime import datetime, timezone

def should_have_run(schedule: str, last_run: str | None) -> bool:
    if not schedule or not last_run:
        return False
    cron = croniter(schedule, datetime.fromisoformat(last_run))
    next_expected = cron.get_next(datetime)
    return datetime.now(timezone.utc) > next_expected
```

### Workflow Registry Storage (Yigthinker Core)

**No new dependency needed.** The registry uses JSON files (`registry.json`, `manifest.json`) read/written with stdlib `json`. PyYAML (already `>=6.0` in core deps) handles `config.yaml` generation. `pathlib` handles directory/version management. This is deliberate -- file-based JSON keeps the registry inspectable, diffable, and zero-infrastructure.

**Why NOT a database for the registry:**
- Workflow count will be small (tens, not thousands). JSON file scan is O(ms).
- Users need to inspect/edit manifests manually when troubleshooting.
- Git-friendly for teams that version-control `~/.yigthinker/workflows/`.
- SQLite would add query capability but at the cost of opacity. Not worth it at this scale.

### MCP Server SDK (Independent Packages)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| mcp | >=1.27.0 | Build MCP servers for PA and UiPath packages | Official Anthropic MCP Python SDK. v1.27.0 (Apr 2026) is current. Requires Python >=3.10. FastMCP provides decorator-based tool definition (`@mcp.tool()`) with automatic JSON Schema generation from type annotations. Supports stdio transport (required for `.mcp.json` integration). The Yigthinker core already uses the MCP client side (`mcp.ClientSession`); the MCP servers use the server side (`FastMCP`). Same package, different entry points. | HIGH |

**MCP server authoring pattern:**

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("yigthinker-mcp-powerautomate")

@mcp.tool()
async def pa_deploy_flow(flow_definition: dict, environment_id: str) -> str:
    """Deploy a Flow definition to Power Automate."""
    # Implementation uses httpx + msal for Dataverse Web API
    ...

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

The MCP servers are **independent packages** with their own `pyproject.toml`. They depend on `mcp>=1.27.0`, `httpx`, and platform-specific auth libraries. They do NOT depend on yigthinker core.

---

## Power Automate Integration Stack (MCP Server: yigthinker-mcp-powerautomate)

### API Strategy -- CRITICAL FINDING

**The `api.flow.microsoft.com` endpoint is officially unsupported.** Microsoft's own documentation (updated May 2025) explicitly states: "Customers should instead use the Dataverse Web APIs for Power Automate." The Flow Management API is subject to breaking changes without notice. Do NOT build on it.

**Correct API path:** Cloud flows are stored as rows in the Dataverse `workflow` entity (category=5). Use the Dataverse Web API (`https://<org>.crm.dynamics.com/api/data/v9.2/workflows`) to create, read, update, and activate/deactivate flows programmatically.

**Authentication implications:** The Dataverse Web API supports both delegated and application permissions (via Azure AD app registration with Dataverse `user_impersonation` scope). This is better than the old Flow API which only supported delegated permissions.

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | >=0.27.0 | HTTP client for Dataverse Web API and Graph API calls | Already used extensively in Yigthinker (Ollama provider, Teams adapter). Async-native, HTTP/2. The MCP server package will use this directly for REST calls -- no Dataverse SDK dependency needed. The Dataverse Web API is standard OData REST, well-suited to raw HTTP. | HIGH |
| msal | >=1.28.0 | Azure AD token acquisition for Dataverse and Graph API | Already used in Teams adapter. `ConfidentialClientApplication.acquire_token_for_client()` for service-to-service auth. Same pattern, different scopes (`https://<org>.crm.dynamics.com/.default` for Dataverse). | HIGH |

**PA API Limitations and Workarounds:**

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Flow definition `clientdata` JSON is complex and fragile | Creating complex flows via API is unreliable | Only create simple flows (HTTP Trigger -> Send Email). Complex logic stays in the generated Python script running on Azure Functions or Task Scheduler. |
| Connection references must exist before flow creation | Cannot programmatically create new connectors | `pa_list_connections` tool queries existing connections. Guide user to create missing ones manually. |
| Flow activation requires the creating user's context | Flows created via API start in Draft state | After API creation, activate via PATCH `statecode=1`. With application permissions this works. |
| Environment ID is required for all calls | User must know their PA environment | `pa_list_connections` doubles as environment validation. Store `PA_ENVIRONMENT_ID` in env vars. |

**Compute deployment for `auto` mode (PA + Azure):**

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| azure-mgmt-web | >=10.0.0 | Programmatic Azure Function App creation and deployment | v10.1.0 is current. `WebSiteManagementClient` creates Function Apps with Timer Trigger for scheduled script execution. Requires `azure-identity` for auth. This is ONLY needed for `auto` deploy mode with Azure subscription. **Optional dependency** -- most PA users will use `guided` mode instead. | MEDIUM |
| azure-identity | >=1.20.0 | Azure credential management for `azure-mgmt-web` | `DefaultAzureCredential` provides environment/CLI/managed-identity auth chain. Required alongside `azure-mgmt-web`. Already well-established -- Microsoft's official auth library. | MEDIUM |
| azure-mgmt-resource | >=23.0.0 | Resource group management (create if needed) | Required for creating the resource group that hosts the Azure Function. Transitive dep pattern with `azure-mgmt-web`. | MEDIUM |

**Important: azure-mgmt-* packages are OPTIONAL.** They belong in the MCP server's optional dependencies, gated behind an `[azure]` extra. Most users will use `guided` mode (Task Scheduler + simple PA notification Flow) and never need these.

### What NOT to Use for PA Integration

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `api.flow.microsoft.com` | Officially unsupported. Subject to breaking changes. | Dataverse Web API (`/api/data/v9.2/workflows`) |
| `PowerPlatform-Dataverse-Client` (Python) | Preview status (Dec 2025). CRUD-focused, no flow-specific helpers. Adds a heavy dependency for what httpx does directly. | Raw httpx + msal against Dataverse Web API |
| `azure-functions` (runtime package) | This is the Azure Functions RUNTIME, not a deployment SDK. Used inside deployed functions, not for creating them. | `azure-mgmt-web` for deployment, `azure-functions` only in generated script `requirements.txt` |
| `msgraph-sdk` / `microsoft-graph` | Heavy SDK for a narrow use case (sending email notifications). The PA notification Flow handles email. | httpx + msal for any Graph calls needed |

---

## UiPath Integration Stack (MCP Server: yigthinker-mcp-uipath)

### API Maturity Assessment

**UiPath Orchestrator OData API is mature and well-documented.** Updated Feb 2026 with improved error responses. Supports all needed operations: package upload, process management, job triggering, trigger creation, queue status queries. REST/OData endpoints are stable across versions.

**Two API paths exist:**

| Path | Auth | Best For |
|------|------|----------|
| UiPath Cloud (`https://cloud.uipath.com/{org}/{tenant}/orchestrator_/odata/`) | OAuth2 client credentials | Cloud customers (majority) |
| UiPath On-Prem / Automation Suite (`https://<server>/odata/`) | API Key or OAuth2 | Enterprise on-prem |

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | >=0.27.0 | HTTP client for UiPath Orchestrator OData API | Same library as PA MCP server. OData is standard REST. Package upload uses `multipart/form-data`. httpx handles both cleanly. | HIGH |

**Why NOT the official UiPath Python SDK (`uipath` package):**

The official `uipath` Python SDK (v2.10.43, Apr 2026) is actively maintained but has significant scope mismatch:
- **Designed for building UiPath-hosted automations**, not for external API access.
- Includes CLI tooling for packaging/deploying from UiPath Studio context.
- Jobs/Processes modules exist but are oriented toward running inside UiPath's platform.
- **Does NOT expose trigger management** (confirmed: not in SDK docs).
- **Does NOT expose package upload** (`uipath publish` CLI exists but requires UiPath project structure).
- Pulls in many dependencies (LangChain integration, agent framework, guardrails) irrelevant to our MCP server use case.

For an MCP server that needs: upload .nupkg, create/manage triggers, query job history -- raw httpx against the OData API is simpler, lighter, and covers all operations.

**Why NOT `TaruDesigns/UIPathAPI`:**

Community-maintained, auto-generated from OpenAPI spec. Covers more endpoints than the official SDK. However:
- Last meaningful update unclear. Auto-generated clients tend to drift from API changes.
- Adds a dependency on a small community project for production infrastructure.
- The OData API is simple enough that a thin httpx wrapper (5-6 functions) is more maintainable than adopting a generated client.

**UiPath OData API key operations:**

| Operation | Endpoint | Method | Notes |
|-----------|----------|--------|-------|
| Upload package | `/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage` | POST (multipart) | .nupkg file as form data |
| Create release | `/odata/Releases` | POST | Links package to folder/environment |
| Start job | `/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs` | POST | Specify release key + robot group |
| Query jobs | `/odata/Jobs` | GET | OData filter/select/orderby |
| Create trigger | `/odata/ProcessSchedules` | POST | Time triggers with cron expression |
| Manage trigger | `/odata/ProcessSchedules({id})` | PATCH/DELETE | Enable/disable/delete |
| Queue status | `/odata/QueueDefinitions` | GET | Queue item counts |

**NuGet package (.nupkg) creation:**

UiPath processes are packaged as .nupkg files (NuGet format). For Python-based automations wrapped in UiPath's Python Activity:

- A .nupkg is just a ZIP file with a `.nuspec` XML manifest and content files.
- Python can create these with `zipfile` (stdlib) + a `.nuspec` template (Jinja2).
- No need for `nuget.exe` or .NET tooling -- the format is simple enough to construct programmatically.
- The MCP server generates the .nupkg containing the Python script + `project.json` pointing to the Python Activity.

```python
import zipfile
from pathlib import Path

def create_nupkg(package_id: str, version: str, script_path: Path, output: Path):
    nuspec = f"""<?xml version="1.0" encoding="utf-8"?>
<package><metadata>
  <id>{package_id}</id><version>{version}</version>
  <description>Generated by Yigthinker</description>
</metadata></package>"""
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{package_id}.nuspec", nuspec)
        z.write(script_path, f"lib/{script_path.name}")
        # Add project.json with Python Activity reference
```

### What NOT to Use for UiPath Integration

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `uipath` (official Python SDK) | Scope mismatch: designed for building UiPath-hosted agents, not external API control. No trigger management. Heavy deps. | httpx against OData API |
| `TaruDesigns/UIPathAPI` | Community auto-generated client. Maintenance risk. OData API is simple enough for direct access. | httpx against OData API |
| `nuget` CLI / .NET SDK | Unnecessary for creating simple .nupkg files. | stdlib `zipfile` + Jinja2 `.nuspec` template |

---

## Dependencies by Package

### Yigthinker Core (pyproject.toml additions)

```toml
[project.optional-dependencies]
workflow = [
    "jinja2>=3.1.6",
    "croniter>=6.0.0",
]
```

**That is it.** Two new dependencies for the entire core. Everything else (json, pathlib, pyyaml, aiosqlite) is already present.

### yigthinker-mcp-powerautomate (independent package)

```toml
[project]
name = "yigthinker-mcp-powerautomate"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.27.0",
    "httpx>=0.27.0",
    "msal>=1.28.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
azure = [
    "azure-mgmt-web>=10.0.0",
    "azure-identity>=1.20.0",
    "azure-mgmt-resource>=23.0.0",
]
```

### yigthinker-mcp-uipath (independent package)

```toml
[project]
name = "yigthinker-mcp-uipath"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.27.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
]
```

UiPath uses OAuth2 client credentials, which httpx handles natively. No `msal` needed (that is Microsoft-specific). UiPath auth is a simple `POST /identity_/connect/token` with client_id + client_secret.

---

## What Already Exists (DO NOT Add)

| Needed For | Already Present | Package |
|------------|-----------------|---------|
| YAML config generation | pyyaml >=6.0 | Core dependency |
| HTTP requests in MCP servers | httpx >=0.27.0 | Core dependency |
| Azure AD auth (PA) | msal >=1.28.0 | Teams optional dep |
| Gateway RPA endpoints | FastAPI + uvicorn | Gateway optional dep |
| Event dedup for RPA callbacks | aiosqlite >=0.20.0 | Core dependency |
| Registry file I/O | json, pathlib (stdlib) | Python stdlib |
| Session context for tools | SessionContext, VarRegistry | Core codebase |
| MCP client (loading MCP servers) | mcp (client side) | Already used lazily |
| Pydantic schemas for tools | pydantic >=2.0.0 | Core dependency |

---

## Version Compatibility Matrix

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| jinja2 >=3.1.6 | Python >=3.7, MarkupSafe >=2.0 | MarkupSafe is the only transitive dep |
| croniter >=6.0.0 | Python >=3.9 | Zero external dependencies |
| mcp >=1.27.0 | Python >=3.10 | MCP servers only (independent packages target >=3.10) |
| azure-mgmt-web >=10.0.0 | Python >=3.9, azure-core, azure-identity | Heavy dep tree. Keep optional. |
| azure-identity >=1.20.0 | Python >=3.9, msal (transitive) | msal is already a dep in PA server |
| httpx >=0.27.0 | Python >=3.8 | Already verified compatible with everything |

**No conflicts** with existing stack. Jinja2 and croniter are lightweight and have no overlapping dependencies with existing packages.

---

## Stack Patterns by Deploy Mode

**If `auto` mode (PA + Azure):**
- MCP server needs: `mcp`, `httpx`, `msal`, `azure-mgmt-web`, `azure-identity`, `azure-mgmt-resource`
- This is the heaviest dependency set. Only install when user has Azure subscription.
- Install: `pip install yigthinker-mcp-powerautomate[azure]`

**If `guided` mode (PA without Azure) -- MOST COMMON:**
- MCP server not needed at all. Yigthinker core generates all artifacts.
- Core needs: `jinja2`, `croniter` only.
- Zero API dependencies. Templates render Python scripts + PA Flow import ZIP + Task Scheduler XML.

**If `auto` mode (UiPath):**
- MCP server needs: `mcp`, `httpx`, `pydantic`
- Lightest MCP server. UiPath OData API is mature and simple.

**If `local` mode (no RPA platform):**
- Core needs: `jinja2`, `croniter` only.
- Generates Python script + OS scheduler config. Zero cloud dependencies.

---

## Sources

- [Jinja2 PyPI](https://pypi.org/project/Jinja2/) -- v3.1.6, Mar 2025 (HIGH confidence)
- [Jinja2 CVE-2025-27516 sandbox bypass fix](https://github.com/advisories/GHSA-cpwx-vrp4-4pq7) -- Critical security fix in 3.1.6 (HIGH confidence)
- [Jinja2 Sandbox docs](https://jinja.palletsprojects.com/en/stable/sandbox/) -- Verified async + sandbox capabilities (HIGH confidence)
- [croniter PyPI](https://pypi.org/project/croniter/) -- v6.2.2, Mar 2026 (HIGH confidence)
- [Power Automate "Work with cloud flows using code"](https://learn.microsoft.com/en-us/power-automate/manage-flows-with-code) -- **Explicitly states api.flow.microsoft.com is unsupported. Use Dataverse Web API.** (HIGH confidence, official Microsoft docs, updated May 2025)
- [Dataverse Web API for Workflows](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/overview) -- Flow CRUD via `/api/data/v9.2/workflows` (HIGH confidence)
- [PA API limitations -- Flow API delegated-only](https://ashiqf.com/tag/delegated-permissions-in-power-automate/) -- Dataverse Web API supports application permissions (MEDIUM confidence)
- [Dataverse SDK for Python (Preview)](https://www.microsoft.com/en-us/power-platform/blog/2025/12/03/dataverse-sdk-python/) -- Announced Ignite 2025, still preview (MEDIUM confidence)
- [PowerPlatform-DataverseClient-Python GitHub](https://github.com/microsoft/PowerPlatform-DataverseClient-Python) -- Preview, Python >=3.10, CRUD only (MEDIUM confidence)
- [UiPath Orchestrator OData API guide](https://docs.uipath.com/orchestrator/automation-cloud/latest/api-guide/introduction) -- Full API reference (HIGH confidence)
- [UiPath Orchestrator release notes Mar 2026](https://docs.uipath.com/orchestrator/automation-cloud/latest/release-notes/march-2026) -- Active development confirmed (HIGH confidence)
- [UiPath Python SDK PyPI](https://pypi.org/project/uipath/) -- v2.10.43, Apr 2026 (HIGH confidence for version; SDK scope verified)
- [UiPath Python SDK GitHub](https://github.com/UiPath/uipath-python) -- Processes, jobs, assets. No trigger management. (HIGH confidence)
- [UiPath package upload via API](https://forum.uipath.com/t/uipath-orchestrator-api-upload-package/16719) -- Multipart POST to UploadPackage endpoint (MEDIUM confidence, community)
- [MCP Python SDK PyPI](https://pypi.org/project/mcp/) -- v1.27.0, Apr 2026, Python >=3.10 (HIGH confidence)
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk) -- FastMCP, stdio/SSE/HTTP transports (HIGH confidence)
- [azure-mgmt-web PyPI](https://pypi.org/project/azure-mgmt-web/) -- v10.1.0 latest (MEDIUM confidence)
- [azure-identity PyPI](https://pypi.org/project/azure-identity/) -- DefaultAzureCredential docs (HIGH confidence)
- [Azure Functions Python reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python) -- Timer trigger, Python 3.13 support (HIGH confidence)

---
*Stack research for: Yigthinker v1.1 Workflow & RPA Bridge*
*Researched: 2026-04-09*
