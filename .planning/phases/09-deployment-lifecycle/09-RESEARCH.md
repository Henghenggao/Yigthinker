# Phase 9: Deployment & Lifecycle - Research

**Researched:** 2026-04-10
**Domain:** Deploy-time artifact generation (Windows Task Scheduler XML, crontab, Power Automate flow_import.zip, UiPath .nupkg stubs) + lifecycle management on an existing filelocked registry
**Confidence:** HIGH on reusable Phase 8 assets and Python stdlib patterns; MEDIUM on PA flow_import.zip exact field values (Microsoft does not publish a hand-craft schema); MEDIUM on UiPath .nupkg minimal stub (docs focus on Studio-generated packages, not hand-crafted ones)

## Summary

Phase 9 builds on the finished Phase 8 `WorkflowRegistry` + `TemplateEngine` to add two file-generating tools (`workflow_deploy`, `workflow_manage`). Almost everything needed is already in the repo: Jinja2 `SandboxedEnvironment` with AST validation, `filelock`-backed atomic writes, `croniter>=6.0.0` (installed: 6.2.2), and the `workflow_generate` reference implementation. There are no new third-party dependencies to add — `pyproject.toml` stays untouched.

The three novel technical surfaces the planner must nail down are: (1) the exact Windows Task Scheduler XML schema — already documented by Microsoft with copy-pasteable namespace and minimum element set; (2) the Power Automate non-solution flow package zip layout — documented as `manifest.json` + `Microsoft.Flow/flows/<GUID>/definition.json`, but Microsoft does not publish a hand-crafting spec so we treat it as "minimum importable shape backed by integration tests against a real export"; (3) cron → Task Scheduler trigger conversion — no library exists, we hand-roll a small dispatcher that handles four canonical cases and degrades to `CalendarTrigger` with a daily schedule for anything exotic.

**Primary recommendation:** Three plans per D-25 of CONTEXT.md. Plan 09-01 (foundation) is the blocker — it owns the registry schema extension, the local-mode templates, and a `cron_to_taskscheduler()` helper. Plans 09-02 and 09-03 run in parallel on top of that foundation. Every template goes through the existing `TemplateEngine.SandboxedEnvironment`; every registry mutation goes through `WorkflowRegistry` filelocked methods; every zipfile is built in memory with `zipfile.ZipFile(..., compression=ZIP_DEFLATED)` and written once. No subprocess, no MCP calls — per D-08/D-15 the tool is architect, not executor.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Local Deploy Mode (DEP-01)**
- **D-01:** `local` mode always emits BOTH `task_scheduler.xml` (Windows) and `crontab.txt` (Linux/macOS) into the version directory's `local_guided/` subfolder. No platform branching, no `os` input parameter.
- **D-02:** Local scheduler artifacts are rendered via Jinja2 from `templates/local/task_scheduler.xml.j2` and `templates/local/crontab.txt.j2`, using the Phase 8 `SandboxedEnvironment`.
- **D-03:** Local mode also renders a `setup_guide.md` explaining how to install each artifact (`schtasks /create /xml ...` and `crontab crontab.txt`).

**Guided Deploy Mode (DEP-02)**
- **D-04:** `guided` mode produces a `{target}_guided/` subfolder with `setup_guide.md`, `flow_import.zip` (PA) or `process_package.zip` (UiPath), `task_scheduler.xml`, `test_trigger.ps1`, `crontab.txt`.
- **D-05:** Artifacts generated at runtime via Jinja2 templates. ZIPs built with `zipfile.ZipFile(mode="w", compression=ZIP_DEFLATED)`. No binary blobs checked in.
- **D-06:** Minimal PA Flow is notification-only: "When an HTTP request is received" → "Send an email (V2)". UiPath package is a Python activity wrapper stub.
- **D-07:** `setup_guide.md` is IM-native: numbered steps, triple-backtick code blocks, no HTML.

**Auto Deploy Mode (DEP-03)**
- **D-08:** `auto` returns a structured `next_steps` payload to the LLM. Shape: `{"mode","target","artifacts_ready","next_steps":[{"tool","args"}],"message"}`. The tool does NOT call MCP servers directly.
- **D-09:** When `deploy_mode="auto"` and no matching MCP server is registered in `ctx.tool_registry`, return an error with a hint to use `guided`. No silent downgrade.

**Mode Auto-Selection (DEP-04)**
- **D-10:** `deploy_mode` is a required input. LLM picks the mode. Tool does no auto-detection beyond the MCP-missing error.

**Registry Schema Extension (DEP-05)**
- **D-11:** Adds fields: `target`, `deploy_mode`, `schedule`, `last_deployed`, `last_run`, `last_run_status`, `failure_count_30d`, `run_count_30d`, `deploy_id`, `current_version` (distinct from Phase 8's `latest_version`).
- **D-12:** Manifest per-version entries add: `deployed_to`, `deploy_mode`, `deploy_id`, `status` (`"active"` | `"superseded"` | `"retired"`).
- **D-13:** Lazy-default on read: `load_index()` and `get_manifest()` fill missing fields with `None`/sensible defaults. First Phase-9 write upgrades the entry. No `schema_version` field yet.
- **D-14:** After any `workflow_deploy` call, metadata is written back via `save_index()` and `save_manifest()` under the existing filelock contract.

**Pause/Resume (LCM-03)**
- **D-15:** Pause/resume flip registry-level `status` ONLY (`"active"` ↔ `"paused"`). No subprocess/MCP call. Returns an instructional next-step block.
- **D-16:** A paused workflow is skipped by `health_check` overdue calculation.

**Rollback (LCM-04)**
- **D-17:** Two-step: (1) flip manifest `active` ↔ `superseded` + update `current_version` pointer; (2) return instructional next-step to re-deploy.
- **D-18:** Registry flip is transactional (under filelock). Re-deploy is explicit and separate.
- **D-19:** `target_version` input is required for rollback.

**Retire (LCM-05)**
- **D-20:** Flips `status="retired"` in both registry.json and the active version's manifest. Files preserved. `list` hides retired by default. Reactivate is out of scope.

**Health Check (LCM-06)**
- **D-21:** Uses `croniter(schedule).get_prev(datetime, now) > last_run` for overdue (active workflows only). Failure rate only if `run_count_30d > 0`; else null.
- **D-22:** Return shape: `[{name, status, schedule, last_run, overdue, failure_rate_pct, alerts: [str]}]`. Empty fields expected until Phase 10.

**Tool Input Design**
- **D-23:** `WorkflowDeployInput(workflow_name, version, target, deploy_mode, schedule, credentials, notify_on_complete)`. When `target="local"`, `deploy_mode` must be `"local"`.
- **D-24:** `WorkflowManageInput(action, workflow_name, target_version)` per design spec Section 4.3.

**Plan Structure**
- **D-25:** Three plans: 09-01 (registry extension + local templates + workflow_deploy shell), 09-02 (guided + auto modes), 09-03 (workflow_manage 7 actions, parallel with 09-02).

### Claude's Discretion

- **D-26:** Exact template variable naming and sub-template structure for guided mode.
- **D-27:** Output format for `list`/`inspect`/`health_check` (JSON vs tabular). LLM-friendly structured dicts default.
- **D-28:** `deploy_id` semantics. Recommended: `{workflow_name}-v{n}-{deploy_mode}-{timestamp}`.

### Deferred Ideas (OUT OF SCOPE)

- `workflow_manage reactivate` (reverse of retire) — not in LCM requirements.
- Mode auto-detection inside the tool.
- Registry `schema_version` field + explicit migration.
- Auto re-deploy on rollback.
- Subprocess-based pause (`schtasks /change`).
- Run history stored locally by `workflow_manage` — all run data comes from Phase 10's `/api/rpa/report`.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEP-01 | `workflow_deploy` local mode generates Windows Task Scheduler XML or crontab entry | §1 Task Scheduler XML schema + §2 crontab format + §5 cron→TaskScheduler conversion |
| DEP-02 | `workflow_deploy` guided mode generates paste-ready artifacts (setup_guide.md, flow_import.zip, task_scheduler.xml, test_trigger.ps1) | §3 PA flow_import.zip structure + §4 UiPath .nupkg stub + §6 zipfile + Jinja2 pattern |
| DEP-03 | `workflow_deploy` auto mode returns structured next-step instructions for LLM | D-08 payload schema already locked — research confirms `ctx.tool_registry` lookup is the right detection path |
| DEP-04 | LLM auto-selects deploy mode; user can override | D-10 locks tool to deterministic `deploy_mode` input; research confirms no library-level auto-detect needed |
| DEP-05 | After deployment, metadata written to Workflow Registry | §8 registry schema extension + existing filelocked `save_index`/`save_manifest` |
| LCM-01 | `list` shows all workflows with status, version, schedule, last run | §8 registry shape + D-20 hide-retired-by-default |
| LCM-02 | `inspect` shows detailed manifest for a specific workflow | Existing `get_manifest()` + lazy-default wrapper |
| LCM-03 | `pause`/`resume` control scheduled triggers | D-15 status-flip-only; no subprocess. Research confirms design spec Section 12.3 matches. |
| LCM-04 | `rollback` reverts to a previous version | §9 two-step transactional rollback pattern (registry flip + instructional next-step) |
| LCM-05 | `retire` permanently deactivates a workflow (preserves files) | D-20 status flip + list hiding. Trivial on existing registry. |
| LCM-06 | `health_check` checks run health of all active workflows | §7 croniter overdue pattern + failure_rate_pct null semantics |

## Project Constraints (from CLAUDE.md)

- **Flat tool registry** — both new tools register under `_register_workflow_tools()` in `yigthinker/registry_factory.py`, same feature gate as Phase 8.
- **YigthinkerTool Protocol** — `name: str`, `description: str`, `input_schema: type[BaseModel]`, `async execute(input, ctx) -> ToolResult`. Tool classes end in `Tool`; input classes end in `Input`.
- **`from __future__ import annotations`** in every new source file.
- **Tools never subprocess-exec or call MCP directly** — Phase 9's "architect, not executor" boundary: `auto` mode returns a next-step list, it does NOT invoke the MCP server.
- **No `os`/`subprocess`/`sys`/`shutil`/`socket`/`http` in generated scripts** — enforced by `_validate_rendered_script()` AST check. Local mode templates render **non-Python** files (XML, crontab, markdown, PowerShell), so they bypass that AST check — use `render()` only for Python output; use new `render_text()` helper for non-Python files.
- **Credential handling** — only `vault://` refs, no plaintext. `_scan_credential_patterns()` runs on config.yaml; should also run on setup_guide.md.
- **`snake_case` file and function names; `PascalCase` classes; 4-space indents.**
- **Pydantic BaseModel with `Literal[...]` for enums; optional fields default to `None`.**
- **Error handling:** wrap `execute()` in try/except, return `ToolResult(is_error=True, content=str(exc))`. Individual tools catch domain-specific exceptions.
- **File I/O:** go through `WorkflowRegistry` methods. Never touch `registry.json` / `manifest.json` files directly from tool code.
- **GSD workflow enforcement:** all code changes must happen inside a GSD phase plan, not ad-hoc edits.

## Standard Stack

### Core (all already installed — NO new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jinja2` | 3.1.6 (installed) | Template rendering via existing `SandboxedEnvironment` | Phase 8 precedent; SSTI-hardened; CVE-2025-27516 fixed in 3.1.6 |
| `croniter` | 6.2.2 (installed) | Cron validation + overdue check | Already a Phase 8 dep; pallets-eco maintained; supports standard 5-field, @-macros, DST |
| `filelock` | 3.25.2 (installed) | Registry concurrency — already wired via `WorkflowRegistry` | Phase 8 established this as the concurrency primitive; no alternative considered |
| `zipfile` (stdlib) | n/a | Bundle `flow_import.zip` and `process_package.zip` in memory | Stdlib — zero cost; `ZipFile(..., compression=ZIP_DEFLATED)` handles everything we need |
| `io.BytesIO` (stdlib) | n/a | In-memory ZIP buffer before writing to registry version dir | Stdlib; the canonical pattern for constructing a zip without a temp file |
| `pydantic` | 2.12.5 (installed) | Tool input schemas with `Literal[...]` enums | Phase 8 precedent; repo-wide standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | n/a | Serialize `definition.json`, `manifest.json`, UiPath `project.json` | All structured artifacts — no YAML required |
| `datetime`, `pathlib`, `uuid` (stdlib) | n/a | `deploy_id` generation, timestamps, paths | Phase 8 precedent |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `cron_to_taskscheduler()` | `python-crontab` library | python-crontab parses crontab files but does NOT emit Task Scheduler XML. No existing library bridges cron→Windows TS. Hand-roll is unavoidable. |
| In-memory `zipfile.ZipFile(BytesIO)` | Write to `tempfile.TemporaryDirectory` then zip | Phase 8 already commits to atomic single-file writes. In-memory keeps the flow simple and testable. |
| `xml.etree.ElementTree` for Task Scheduler XML | String templating via Jinja2 | The TS XML schema is stable and small — Jinja2 is simpler and matches Phase 8's pattern. ElementTree adds verbosity for no win. |
| Package building with `nuget pack` subprocess | Hand-crafted `.nupkg` (zip + `.nuspec`) | Design spec D-06 says UiPath package is a stub. We never invoke `nuget`. The .nupkg is just a renamed zip with a `.nuspec` manifest + `project.json` + a placeholder `Main.xaml`. |

**Installation:** None. `pyproject.toml` is untouched. Phase 9 inherits all deps from Phase 8's `workflow` optional group:

```toml
[project.optional-dependencies]
workflow = [
    "jinja2>=3.1.6",
    "croniter>=6.0.0",
]
```

**Version verification (confirmed 2026-04-10 against local `pip show`):**
- `jinja2` 3.1.6 — installed, meets `>=3.1.6` CVE-patched floor
- `croniter` 6.2.2 — installed, latest stable (2026-03-15)
- `filelock` 3.25.2 — installed
- All transitively available via the `workflow` optional group

## Architecture Patterns

### Recommended File Layout (extends Phase 8)

```
yigthinker/tools/workflow/
├── workflow_deploy.py          # NEW — WorkflowDeployTool
├── workflow_manage.py          # NEW — WorkflowManageTool
├── registry.py                 # EDIT — add lazy-default reads (D-13)
├── template_engine.py          # EDIT — add render_text(), render_zip_bundle()
└── templates/
    ├── base/                   # UNCHANGED from Phase 8
    ├── power_automate/         # EXTEND
    │   ├── main.py.j2          # (Phase 8)
    │   ├── flow_definition.json.j2     # NEW — PA definition.json
    │   ├── flow_manifest.json.j2       # NEW — PA top-level manifest.json
    │   ├── setup_guide.md.j2           # NEW
    │   └── test_trigger.ps1.j2         # NEW
    ├── uipath/                 # EXTEND
    │   ├── main.py.j2          # (Phase 8)
    │   ├── project.json.j2             # NEW — UiPath project.json
    │   ├── main_xaml.j2                # NEW — UiPath Main.xaml stub
    │   ├── nuspec.j2                   # NEW — .nuspec for nupkg
    │   ├── setup_guide.md.j2           # NEW
    │   └── test_trigger.ps1.j2         # NEW
    └── local/                  # NEW DIRECTORY
        ├── task_scheduler.xml.j2
        ├── crontab.txt.j2
        └── setup_guide.md.j2
```

### Pattern 1: Non-Python Template Rendering (bypass AST check)

**What:** Phase 8's `render()` method always runs `_validate_rendered_script()` which calls `ast.parse(code)`. That fails on XML, crontab, markdown, etc. Add a new method that renders through the SANDBOXED env but skips AST check and instead runs the credential scanner.

**When to use:** Any non-Python artifact (XML, YAML, JSON, markdown, PowerShell, crontab).

**Example:**
```python
# Source: extends existing template_engine.py pattern
class TemplateEngine:
    def render_text(self, template_path: str, context: dict) -> str:
        """Render a non-Python template through SandboxedEnvironment.

        Runs credential scan but skips Python AST validation.
        """
        template = self._env.get_template(template_path)
        rendered = template.render(**context)
        issues = _scan_credential_patterns(rendered)
        if issues:
            raise ValueError(f"Rendered {template_path} contains credentials: {issues}")
        return rendered
```

### Pattern 2: In-Memory ZIP Bundle

**What:** Render multiple templates, bundle into a single `.zip` in memory, return bytes that the tool writes to the version directory via `WorkflowRegistry.create()` or direct write.

**When to use:** `flow_import.zip` (PA) and `process_package.zip` / `.nupkg` (UiPath).

**Example:**
```python
# Source: Python stdlib zipfile docs + Phase 8 render_config pattern
import io
import zipfile

def render_pa_flow_import_zip(engine: TemplateEngine, context: dict) -> bytes:
    """Build a minimal PA non-solution flow package in memory."""
    manifest = engine.render_text("power_automate/flow_manifest.json.j2", context)
    definition = engine.render_text("power_automate/flow_definition.json.j2", context)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest)
        # PA layout: Microsoft.Flow/flows/{GUID}/definition.json
        flow_guid = context["flow_guid"]  # uuid4 hex, minted at tool call time
        zf.writestr(
            f"Microsoft.Flow/flows/{flow_guid}/definition.json",
            definition,
        )
    return buf.getvalue()
```

**Critical gotchas:**
- **Always use forward-slash paths inside the zip** (`Microsoft.Flow/flows/...`). ZIP standard is POSIX; Windows paths break PA import.
- **`writestr()` takes a str for filename and str or bytes for content** — if you pass `pathlib.Path`, you get Windows separators that Power Automate refuses.
- **Write `BytesIO` contents once** — `buf.getvalue()` returns the full bytes after the `with` block closes the ZipFile (which flushes the central directory).

### Pattern 3: Cron → Task Scheduler Trigger Dispatcher

**What:** Cron has 5 fields (`min hour dom mon dow`); Task Scheduler has typed trigger elements (`TimeTrigger`, `CalendarTrigger` with `ScheduleByDay`/`ScheduleByMonth`/`ScheduleByWeek`). No library bridges these. Hand-roll a small dispatcher that recognizes the four canonical shapes and falls back to `CalendarTrigger > ScheduleByDay` with a `StartBoundary` derived from `croniter.get_next()`.

**When to use:** Local deploy mode's `task_scheduler.xml` generation.

**Supported canonical shapes (fallthrough order):**

| Cron | Interpretation | Task Scheduler form |
|------|---------------|---------------------|
| `M H * * *` | Daily at H:M | `<CalendarTrigger><StartBoundary>...</StartBoundary><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>` |
| `M H D * *` | Monthly on day D at H:M | `<CalendarTrigger>...<ScheduleByMonth><DaysOfMonth><Day>D</Day></DaysOfMonth><Months><January/>...<December/></Months></ScheduleByMonth></CalendarTrigger>` |
| `M H * * W` | Weekly on weekday W at H:M | `<CalendarTrigger>...<ScheduleByWeek><DaysOfWeek><Monday/>...</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>` |
| `0 */N * * *` | Every N hours | `<CalendarTrigger>...<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay><Repetition><Interval>PTNH</Interval><Duration>P1D</Duration></Repetition></CalendarTrigger>` |

Anything else → use `CalendarTrigger > ScheduleByDay` with `StartBoundary = croniter.get_next()` and warn in the `setup_guide.md` that the user should verify the trigger matches the original cron intent.

**Example:**
```python
# Source: hand-rolled based on Task Scheduler XML schema docs
# https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema-elements
from croniter import croniter
from datetime import datetime

_WEEKDAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
_MONTH_ELEMS = "<January/><February/><March/><April/><May/><June/>" \
               "<July/><August/><September/><October/><November/><December/>"

def cron_to_ts_trigger(schedule: str, start_ref: datetime) -> dict:
    """Parse a 5-field cron expression into Task Scheduler trigger template vars.

    Returns a dict the task_scheduler.xml.j2 template consumes.
    Always includes a next_run StartBoundary (ISO 8601 local time).
    """
    croniter(schedule)  # validates — raises on invalid
    itr = croniter(schedule, start_ref)
    next_run = itr.get_next(datetime)

    parts = schedule.strip().split()
    if len(parts) != 5:
        return {"kind": "calendar_daily", "start_boundary": next_run.isoformat(),
                "needs_manual_review": True}

    minute, hour, dom, mon, dow = parts

    # Daily: M H * * *
    if dom == "*" and mon == "*" and dow == "*":
        return {"kind": "calendar_daily", "start_boundary": next_run.isoformat()}

    # Monthly-on-Nth: M H D * *
    if dom.isdigit() and mon == "*" and dow == "*":
        return {"kind": "calendar_monthly", "day_of_month": int(dom),
                "start_boundary": next_run.isoformat()}

    # Weekly: M H * * W
    if dom == "*" and mon == "*" and dow.isdigit():
        return {"kind": "calendar_weekly",
                "day_of_week": _WEEKDAY_NAMES[int(dow) % 7],
                "start_boundary": next_run.isoformat()}

    # Every-N-hours: 0 */N * * *
    if minute == "0" and hour.startswith("*/") and dom == "*" and mon == "*" and dow == "*":
        n = int(hour[2:])
        return {"kind": "calendar_hourly", "interval_hours": n,
                "start_boundary": next_run.isoformat()}

    # Fallback: daily with a warning
    return {"kind": "calendar_daily", "start_boundary": next_run.isoformat(),
            "needs_manual_review": True}
```

The Jinja2 template consumes this via `{% if trigger.kind == "calendar_daily" %}...{% elif ... %}...{% endif %}`.

### Pattern 4: Registry Lazy-Default Reads (D-13)

**What:** Phase 8 entries lack Phase 9 fields. Wrap `load_index()` and `get_manifest()` reads with a `_fill_defaults()` helper so Phase 9 code never sees `KeyError`.

**When to use:** Inside `workflow_deploy.py` and `workflow_manage.py`, never edit the registry class signatures — just add a helper.

**Example:**
```python
# Source: designed for Phase 9 per D-13
_PHASE9_DEFAULTS = {
    "target": None,
    "deploy_mode": None,
    "schedule": None,
    "last_deployed": None,
    "last_run": None,
    "last_run_status": None,
    "failure_count_30d": 0,
    "run_count_30d": 0,
    "deploy_id": None,
    "current_version": None,  # None means "use latest_version"
}

def _fill_workflow_defaults(entry: dict) -> dict:
    """Lazy-fill Phase 9 fields on a Phase 8 registry entry. Does NOT write back."""
    for key, default in _PHASE9_DEFAULTS.items():
        entry.setdefault(key, default)
    return entry
```

Calling `_fill_workflow_defaults()` inside `workflow_manage.list()` keeps Phase 8 entries readable without mutating them. First Phase 9 write that calls `save_index()` automatically persists the new fields via the existing merge.

### Anti-Patterns to Avoid

- **Hand-editing `registry.json` from tool code.** Always go through `WorkflowRegistry.save_index()` / `save_manifest()` — they own the filelock and the atomic replace. Anything else races with Phase 10's `/api/rpa/report`.
- **Using `render()` (which runs AST check) on non-Python files.** It will fail with "syntax error" on XML/YAML/markdown. Use `render_text()`.
- **Including the full workflow directory as a ZIP inside `flow_import.zip`.** PA only wants its own manifest + definition. Don't nest the Python script.
- **Calling `subprocess.run(["schtasks", ...])` from `workflow_deploy`.** Violates D-08 "architect, not executor." The tool only writes files.
- **Reading `latest_version` as a proxy for `current_version`.** Phase 8's `latest_version` is a monotonic max; Phase 9's `current_version` is the active pointer that rollback can move backward. They ARE different. Never conflate.
- **Building the ZIP inside `version_dir` directly.** Race risk if the tool is interrupted mid-write. Build in `BytesIO`, then single `Path.write_bytes()` at the end.
- **Catching `Exception` broadly in the rollback registry flip.** The flip is a two-step registry mutation — if step 2 fails after step 1 succeeded, you're in an inconsistent state. Wrap both in a single `save_index()` call (atomic under filelock) OR do an explicit revert on step-2 failure.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Filesystem concurrency for registry | Any new lock file, thread lock, or async lock | Existing `WorkflowRegistry` + `filelock` | Phase 8 already built the merge-based atomic write (`read-inside-lock + dict.update`). Two locks = deadlock risk. |
| Cron expression parsing / validation | Regex or string-split validation | `croniter(schedule)` in a try/except ValueError | croniter handles every edge case (`*/N`, `1-5`, `@daily`, DST, 6-field with seconds). Regex will miss things. |
| Jinja2 environment | New `Environment()` or `Template()` | `TemplateEngine._env` (SandboxedEnvironment) | Phase 8's env has the SSTI guards + AST check already wired. A second env bypasses them. |
| ZIP creation | Writing files to temp dir then shelling to `zip`/`7z` | `zipfile.ZipFile(BytesIO(), ..., ZIP_DEFLATED)` | Stdlib. Cross-platform. No temp files. No subprocess (forbidden anyway). |
| Credential scanning | New regex patterns | `template_engine._scan_credential_patterns()` | Already reviewed in Phase 8. Keep one source of truth. |
| Task Scheduler XML parsing | ElementTree parse + walk | Direct string templating in `task_scheduler.xml.j2` | TS XML is write-only for us. Parsing is unnecessary complexity. |
| JSON writes | Manual `open()`/`write()`/`close()` | Use existing `save_index`/`save_manifest` for registry; use `Path.write_text(json.dumps(..., indent=2))` for tool outputs that bypass registry | Registry is already atomic. Non-registry files are rendered inside a version dir that the registry owns. |
| UUID / deploy_id generation | Hand-rolled hash | `f"{name}-v{n}-{mode}-{int(datetime.now(timezone.utc).timestamp())}"` per D-28 | Human-debuggable > UUID opacity. |

**Key insight:** Phase 8 already built 90% of Phase 9's machinery. The only genuinely new code is: (a) three Jinja2 sub-template sets, (b) one cron→TS-trigger dispatcher, (c) two new tool classes, (d) the lazy-default helper. Anything that feels like "new infrastructure" is probably duplicating Phase 8.

## Runtime State Inventory

This is not a rename/refactor phase — it adds new tools and a backward-compatible schema extension on top of Phase 8's registry. However, the schema extension touches stored data, so we document it here explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing `~/.yigthinker/workflows/registry.json` entries from Phase 8 lack Phase 9 fields (`target`, `deploy_mode`, `schedule`, `current_version`, etc.) | **Code edit only** — `_fill_workflow_defaults()` on read; first Phase 9 `save_index()` write upgrades the entry. No data migration pass per D-13. |
| Stored data | Existing `~/.yigthinker/workflows/{name}/manifest.json` entries lack per-version `deployed_to`, `deploy_mode`, `deploy_id`, `status` | **Code edit only** — same lazy-default pattern on `get_manifest()`. Retire/rollback are the first operations that mutate per-version entries. |
| Live service config | None — Phase 9 tool only writes files to disk. It does NOT register anything with Task Scheduler, cron, PA, or UiPath (D-08, D-15). | None. |
| OS-registered state | None from Yigthinker itself. (Generated `task_scheduler.xml` is installed by the USER running `schtasks /create /xml`, not by us.) | None. The setup_guide.md documents what the user installs; the tool doesn't register state. |
| Secrets/env vars | None — `credentials: dict[str, str]` input accepts only `vault://` refs; rendered config.yaml references them by name. No new env var dependencies. | None. |
| Build artifacts / installed packages | None — no new entry points, no new wheels, no new pip-installed subpackages. | None. |

**Canonical question:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* → Only the on-disk registry in `~/.yigthinker/workflows/`, and it is handled by lazy defaults (no active migration). User-installed scheduler tasks and imported PA flows are owned by the user's OS and RPA platform — deliberately outside the tool's mutation surface.

## Common Pitfalls

### Pitfall 1: SSTI through Workflow Name in setup_guide.md

**What goes wrong:** `workflow_name` is user-controllable (LLM can pass anything). If a setup guide template does `## Workflow: {{ workflow_name }}` and the name contains `{{ self.__class__.__mro__[-1] }}`, the sandbox still blocks dangerous attribute access — but only because `SandboxedEnvironment` is enforced. A developer copy-pasting a template that uses a bare `Environment()` re-opens the hole.

**Why it happens:** Phase 8's PITFALLS.md already flagged this for config.yaml. Phase 9 adds 8+ new templates; a single miss matters.

**How to avoid:**
- ALL new templates go through `TemplateEngine._env` (confirmed `SandboxedEnvironment` in the existing test `test_sandboxed_environment`).
- Write an extended version of `test_ssti_blocked` that fires a `{{ 7*7 }}` payload through `workflow_name` and asserts "49" does not appear standalone in every new template (task_scheduler.xml, crontab.txt, setup_guide.md, flow_definition.json, etc.).
- Markdown is particularly dangerous because humans don't read rendered output for template syntax — they see "## Workflow: foo" and assume it's safe. Test defends it.

**Warning signs:** Any new `render_*` method that imports `jinja2.Template` directly. Any template that uses `{{ variable | safe }}`.

### Pitfall 2: Credential Leakage into setup_guide.md

**What goes wrong:** The `credentials: dict[str, str]` input is supposed to be `vault://` refs only, but nothing validates that. An LLM passes `{"db_password": "correct-horse-battery-staple"}` → renders into setup_guide.md → user commits it to git.

**Why it happens:** Phase 8's `_scan_credential_patterns` runs only on `config.yaml`. setup_guide.md is new ground.

**How to avoid:**
- Add `_scan_credential_patterns()` call inside `render_text()` for ALL non-Python templates.
- Validate `WorkflowDeployInput.credentials` values at tool entry: reject any value not matching `^vault://` or `^\{\{` (placeholder).
- Add a test that passes a plaintext password via credentials dict and asserts the tool raises or redacts.

**Warning signs:** A template that interpolates `{{ credentials.some_key }}` without `| default('vault://TODO')`. Any test fixture that uses real-looking credentials.

### Pitfall 3: Registry Schema Extension Breaking Phase 8 Manifests

**What goes wrong:** A Phase 8 entry like `{"status": "active", "latest_version": 2, ...}` is read by Phase 9 `workflow_manage.inspect`, which does `entry["current_version"]` → KeyError → tool returns `is_error=True` → user thinks their workflow is corrupted.

**Why it happens:** D-13 says "lazy-default on read" but it's easy to forget the helper inside one of seven `workflow_manage` actions.

**How to avoid:**
- Write the lazy-default helper ONCE in `workflow_manage.py` (or `registry.py`) and call it at every read site.
- Add a regression test: create a fake registry.json with ONLY Phase 8 fields, run every `workflow_manage` action against it, assert no KeyError.
- Never write `entry["current_version"]` without going through the helper. Use a linter rule / grep check in CI if possible.

**Warning signs:** `entry["<new_field>"]` anywhere in Phase 9 code. `entry.get("<new_field>")` is safe but inconsistent — use the helper for uniform behavior.

### Pitfall 4: Rollback Race with Concurrent Deploy

**What goes wrong:** User runs `workflow_manage rollback name --target_version 1` at 10:00:00. At 10:00:01 the LLM runs `workflow_deploy name` which reads `current_version=2`, writes v3 metadata, and clobbers the rollback. The on-wire filelock prevents write corruption, but the logical state is wrong.

**Why it happens:** Phase 8's merge-based `save_index` protects field-level writes but doesn't serialize read-modify-write logic.

**How to avoid:**
- Rollback's registry flip MUST be a single `save_index()` call that reads inside the lock and writes inside the lock. (Phase 8's implementation already does read-inside-lock, but Phase 9 code needs to follow suit and not read outside then write inside.)
- Emit a "rollback completed, current_version set to vN — deploy the new active version via workflow_deploy" instructional next-step so the follow-up deploy is user-driven, not auto-queued.
- Document in the tool description: "rollback is transactional for registry state; do not run deploy concurrently."

**Warning signs:** `index = registry.load_index(); index["workflows"][name]["current_version"] = target_version; registry.save_index(index)` — this has a TOCTOU window. The read must happen INSIDE the save_index operation, or save_index must accept a patch function.

**Mitigation pattern (recommended):** Add a `registry.save_index_with_patch(fn)` method where `fn(current_dict) -> patched_dict` runs inside the filelock. Or — simpler — the existing `save_index()` already merges dicts, so for rollback just pass `{"workflows": {name: {"current_version": target_version}}}` and let the merge handle it. No read-before-write at all.

### Pitfall 5: Lazy-Default Reads Masking Corruption

**What goes wrong:** Registry file is genuinely corrupted (truncated JSON, wrong encoding). `load_index()` raises. Lazy-default wrapper catches it and returns `{}` → user sees "no workflows" → thinks everything was deleted.

**Why it happens:** Defensive coding over broad `except Exception`.

**How to avoid:**
- Lazy defaults fill MISSING FIELDS on a loaded dict. They do NOT catch file-level errors.
- Let `JSONDecodeError` propagate from `load_index()` — the tool turns it into `ToolResult(is_error=True, content="Registry file corrupted: ...")` with a recovery hint.
- Research PITFALLS.md item 3 already recommends `.bak` fallback; Phase 8 deferred it. Phase 9 should NOT silently pretend an empty registry is fine.

**Warning signs:** `try: return load_index() except Exception: return {"workflows": {}}`.

### Pitfall 6: Health Check Wrong for Just-Deployed Workflows

**What goes wrong:** Workflow deployed at 10:00 with schedule `0 8 5 * *` (monthly 5th 8am). Health check runs at 10:01 on the 1st of the month. `last_run` is None. `get_prev(datetime, now)` returns the 5th of the PREVIOUS month. `None > any_datetime` → TypeError or always-overdue.

**Why it happens:** Overdue calculation uses `croniter(schedule).get_prev(datetime, now) > last_run`, but `last_run` is `None` until the first execution reports.

**How to avoid:**
- Treat `last_run is None` as "never run" → check against `last_deployed` instead: if `get_prev(datetime, now) > last_deployed` AND `last_deployed` is more than one schedule interval ago, flag overdue. Otherwise treat as "not yet due, freshly deployed".
- Even simpler: if `last_run is None and last_deployed is not None and last_deployed < get_prev(datetime, now)`, overdue. Else not overdue.
- Add a test fixture with a fresh deploy + no last_run, assert `overdue == False`.

**Warning signs:** `if last_run is None: last_run = datetime.min` — this makes every new workflow "overdue" and triggers alert fatigue.

### Pitfall 7: Path Separators in Generated Artifacts

**What goes wrong:** On Windows, `Path("workflows") / "monthly_ar_aging" / "v1" / "main.py"` becomes `workflows\monthly_ar_aging\v1\main.py`. If this gets string-interpolated into a template and written to a crontab file or a PowerShell script, it breaks on Linux/Mac (crontab) or breaks in the ZIP (PA refuses backslash paths).

**Why it happens:** Yigthinker runs on Windows (per CLAUDE.md constraint). Developers see forward slashes on Linux dev boxes and Windows treats them interchangeably — but the files it generates target multiple platforms.

**How to avoid:**
- For crontab.txt: use `str(path).replace("\\", "/")` or `path.as_posix()` before templating. Crontab is POSIX-only.
- For task_scheduler.xml `<WorkingDirectory>`: use native Windows paths. This is Windows-only output.
- For ZIP internal paths: hard-code forward slashes in the f-string, never use `Path` objects in `zf.writestr()`.
- For setup_guide.md: show both a Windows example (`C:\workflows\...`) and a POSIX example (`~/yigthinker/workflows/...`) since the guide crosses platforms.

**Warning signs:** `zf.writestr(Path("Microsoft.Flow") / "flows" / guid / "definition.json", ...)` — Path concatenation goes through os.sep, which is backslash on Windows.

### Pitfall 8: ZIP_STORED vs ZIP_DEFLATED for PA Import

**What goes wrong:** Default `zipfile.ZipFile(mode="w")` uses `ZIP_STORED` (no compression). Power Automate's import UI has been reported to reject uncompressed zips in some edge cases, and a STORED zip of the same content is 2-3x larger, which matters when users paste it into IM.

**Why it happens:** Developers assume default mode is fine; no one specifies compression until a bug forces it.

**How to avoid:**
- D-05 already specifies `ZIP_DEFLATED`. Enforce in code.
- `zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED)` — note: `ZIP_DEFLATED` requires the `zlib` module, which is always present in CPython 3.11. No extras needed.

**Warning signs:** `zipfile.ZipFile(buf, "w")` without a compression arg.

## Code Examples

### Example 1: Daily Task Scheduler XML (8am daily)

```xml
<!-- Source: https://learn.microsoft.com/en-us/windows/win32/taskschd/time-trigger-example--xml-
     Adapted: CalendarTrigger with ScheduleByDay (matches "0 8 * * *") -->
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2026-04-10T00:00:00</Date>
    <Author>Yigthinker</Author>
    <Description>Auto-generated: monthly_ar_aging v1</Description>
    <URI>\Yigthinker\monthly_ar_aging</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-11T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\Python311\python.exe</Command>
      <Arguments>main.py</Arguments>
      <WorkingDirectory>C:\Users\username\.yigthinker\workflows\monthly_ar_aging\v1</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

**Key notes:**
- `<?xml version="1.0" encoding="UTF-16"?>` — Task Scheduler stores XML as UTF-16 on disk. BUT `schtasks /create /xml` accepts UTF-8 and UTF-16 files. Use UTF-8 for simpler text handling; `<?xml encoding="UTF-16"?>` is NOT mandatory.
- `xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"` is mandatory.
- `<Command>` must be an absolute path to `python.exe`, resolved at generation time via `sys.executable`. Per PITFALLS Pitfall 7.
- `<WorkingDirectory>` must be the absolute path of the workflow version directory. Relative paths resolve against Task Scheduler's CWD (Windows\System32), which breaks all `from checkpoint_utils import ...` imports.

### Example 2: Monthly-on-5th Task Scheduler XML (0 8 5 * *)

```xml
<!-- Replace the <Triggers> block in Example 1 with: -->
<Triggers>
  <CalendarTrigger>
    <StartBoundary>2026-05-05T08:00:00</StartBoundary>
    <Enabled>true</Enabled>
    <ScheduleByMonth>
      <DaysOfMonth>
        <Day>5</Day>
      </DaysOfMonth>
      <Months>
        <January/><February/><March/><April/><May/><June/>
        <July/><August/><September/><October/><November/><December/>
      </Months>
    </ScheduleByMonth>
  </CalendarTrigger>
</Triggers>
```

### Example 3: Portable crontab.txt

```
# Auto-generated by Yigthinker — monthly_ar_aging v1
# Install with: crontab crontab.txt
# Verify with:  crontab -l

# Schedule: monthly on the 5th at 08:00
# PATH and working dir must be explicit — cron runs with a minimal env
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 8 5 * * cd /home/username/.yigthinker/workflows/monthly_ar_aging/v1 && /usr/bin/python3 main.py >> run.log 2>&1
```

**Key notes:**
- **Always set PATH explicitly** — system cron runs with almost no PATH by default. Scripts that call `psql`, `curl`, etc. will fail without it.
- **Always `cd` to the workflow directory** — relative `checkpoint_utils` imports and relative `config.yaml` reads require it.
- **Always redirect stdout/stderr** (`>> run.log 2>&1`) — otherwise failures go to the user's mailbox silently.
- **Use absolute `python3` path** — resolve at generation time. On Linux, `which python3` at generation time gives `/usr/bin/python3` typically.
- **End with a newline** — POSIX crontab parsers require a trailing newline or silently skip the last entry.

### Example 4: Minimal PA Flow Import Zip (notification-only)

**Zip layout:**
```
flow_import.zip
├── manifest.json
└── Microsoft.Flow/
    └── flows/
        └── {flow_guid_uuid4_hex}/
            └── definition.json
```

**manifest.json (minimal):**
```json
{
  "schema": "1.0",
  "details": {
    "displayName": "monthly_ar_aging Notifier",
    "description": "Sends email notification when AR aging script completes",
    "createdTime": "2026-04-10T00:00:00Z",
    "packageTelemetryId": "yigthinker-generated"
  },
  "resources": {
    "{flow_guid}": {
      "id": "{flow_guid}",
      "name": "monthly_ar_aging_notifier",
      "type": "Microsoft.Flow/flows",
      "suggestedCreationType": "New",
      "creationType": "New",
      "details": {
        "displayName": "monthly_ar_aging Notifier"
      },
      "configurableBy": "User",
      "hierarchy": "Root",
      "dependsOn": []
    }
  }
}
```

**definition.json (HTTP trigger → Send Email V2 skeleton):**
```json
{
  "name": "monthly_ar_aging_notifier",
  "id": "/providers/Microsoft.Flow/flows/{flow_guid}",
  "type": "Microsoft.Flow/flows",
  "properties": {
    "displayName": "monthly_ar_aging Notifier",
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "parameters": {
        "$connections": {
          "defaultValue": {},
          "type": "Object"
        }
      },
      "triggers": {
        "manual": {
          "type": "Request",
          "kind": "Http",
          "inputs": {
            "schema": {
              "type": "object",
              "properties": {
                "recipients": {"type": "array", "items": {"type": "string"}},
                "period": {"type": "string"},
                "file_path": {"type": "string"},
                "status": {"type": "string"}
              }
            }
          }
        }
      },
      "actions": {
        "Send_an_email_(V2)": {
          "runAfter": {},
          "type": "OpenApiConnection",
          "inputs": {
            "host": {
              "connectionName": "shared_office365",
              "operationId": "SendEmailV2",
              "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365"
            },
            "parameters": {
              "emailMessage/To": "@{join(triggerBody()?['recipients'], ';')}",
              "emailMessage/Subject": "@{concat('AR Aging Report: ', triggerBody()?['period'])}",
              "emailMessage/Body": "<p>Monthly AR aging completed. Status: @{triggerBody()?['status']}. File: @{triggerBody()?['file_path']}</p>",
              "emailMessage/Importance": "Normal"
            }
          }
        }
      },
      "outputs": {}
    }
  }
}
```

**IMPORTANT caveats (LOW confidence on exact structure — verify with integration test):**
- Microsoft does not publish a hand-crafting spec for non-solution flow packages. The structure above is derived from multiple community sources editing real exports.
- `connections.json` is NOT included here. Per Microsoft docs: "if `connections.json` is absent, Power Automate will require you to remap connections manually during import" — which is exactly what we want. The user imports → PA prompts them to pick their Outlook connection → done.
- The `{flow_guid}` placeholder must be a new uuid4 hex string, identical in the path, the manifest resource key, and the definition `id`. Mint it at tool-call time with `uuid.uuid4().hex`.
- Tests MUST verify that the generated zip imports cleanly into a real PA environment at least once during Phase 9 acceptance. Automated schema validation is not sufficient.
- **Recommended Wave 0 step:** Manually export a minimal "HTTP trigger → Send email" flow from an existing PA tenant, save the real zip as a golden fixture in `tests/fixtures/pa_reference_flow.zip`. Use it as a structural reference for Phase 9 template rendering. Do not commit real credentials or display names.

### Example 5: Minimal UiPath project.json (Python-activity stub)

```json
{
  "name": "monthly_ar_aging",
  "description": "Auto-generated by Yigthinker — runs monthly_ar_aging v1 Python script",
  "main": "Main.xaml",
  "dependencies": {
    "UiPath.System.Activities": "[23.10.7]",
    "UiPath.Python.Activities": "[1.7.0]"
  },
  "webServices": [],
  "entitiesStores": [],
  "schemaVersion": "4.0",
  "studioVersion": "23.10.0.0",
  "projectVersion": "1.0.0",
  "runtimeOptions": {
    "autoDispose": false,
    "isPausable": true,
    "isAttended": false,
    "requiresUserInteraction": false,
    "supportsPersistence": false,
    "excludedLoggedData": ["Private:*", "*password*"],
    "executionType": "Workflow",
    "readyForPiP": false,
    "startsInPiP": false
  },
  "designOptions": {
    "projectProfile": "Development",
    "outputType": "Process",
    "libraryOptions": {
      "includeOriginalXaml": false,
      "privateWorkflows": []
    },
    "processOptions": {
      "ignoredFiles": []
    },
    "modernBehavior": true
  },
  "expressionLanguage": "VisualBasic",
  "entryPoints": [
    {
      "filePath": "Main.xaml",
      "uniqueId": "{entry_point_guid}",
      "input": [],
      "output": []
    }
  ],
  "isTemplate": false,
  "targetFramework": "Windows"
}
```

**Stub `Main.xaml` (opaque to Yigthinker — just a placeholder to satisfy project.json):**
```xml
<Activity mc:Ignorable="sap sap2010" x:Class="Main" xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation" xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation" xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib" xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=mscorlib" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <!-- Yigthinker stub: users must open in Studio and add a Python Scope + Run Python Script activity pointing at main.py -->
    <WriteLine Text="Stub — configure Python Scope in Studio" />
  </Sequence>
</Activity>
```

**CRITICAL caveat:** Yigthinker does NOT attempt to hand-craft a working XAML that invokes a Python activity. Per D-06 the UiPath guided package is a STUB — the setup_guide.md tells the user to open the process in UiPath Studio, add a Python Scope activity pointing at `main.py`, and republish. The reason: XAML with live UiPath activities requires proprietary serialized type data that changes across UiPath versions. A stub XAML is honest about the seam.

**Nuspec file (`.nupkg` is a renamed zip with a `.nuspec` at the root):**
```xml
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>monthly_ar_aging</id>
    <version>1.0.0</version>
    <title>monthly_ar_aging</title>
    <authors>Yigthinker</authors>
    <owners>Yigthinker</owners>
    <description>Auto-generated by Yigthinker</description>
    <releaseNotes>v1 initial generation</releaseNotes>
    <projectUrl>https://github.com/FinCode-Dev/Yigthinker</projectUrl>
    <tags>yigthinker automation</tags>
  </metadata>
  <files>
    <file src="project.json" target="project.json" />
    <file src="Main.xaml" target="Main.xaml" />
  </files>
</package>
```

**Zip layout for `.nupkg` (which is just a zip):**
```
process_package.zip (a.k.a. monthly_ar_aging.1.0.0.nupkg)
├── monthly_ar_aging.nuspec
├── project.json
└── Main.xaml
```

### Example 6: croniter Overdue Check

```python
# Source: croniter 6.2.2 docs + design spec LCM-06
from croniter import croniter
from datetime import datetime, timezone

def is_overdue(schedule: str, last_run: str | None, last_deployed: str | None) -> bool:
    """Compute whether an active workflow has missed its most recent scheduled run.

    Guards against the "just deployed, no runs yet" case (Pitfall 6).
    """
    now = datetime.now(timezone.utc)
    try:
        prev_scheduled = croniter(schedule, now).get_prev(datetime)
    except (ValueError, KeyError):
        return False  # invalid schedule — don't alert, surface elsewhere

    # Use last_run if available; otherwise fall back to last_deployed
    if last_run:
        reference = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
    elif last_deployed:
        reference = datetime.fromisoformat(last_deployed.replace("Z", "+00:00"))
    else:
        return False  # never deployed, never ran — definitionally not overdue

    # Overdue means the most recent scheduled time is AFTER our reference point
    return prev_scheduled > reference
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Environment()` (Jinja2 default) | `SandboxedEnvironment()` | CVE-2024-56201, CVE-2025-27516 — fixed in 3.1.5 and 3.1.6 | Mandatory for any template rendering user-controllable input; Phase 8 already enforces |
| PA Classic API Keys | MSAL `ConfidentialClientApplication` | ~2024 | Not directly relevant to Phase 9 (we don't call PA API), but the `guided` setup_guide.md must tell users to configure the Outlook connector in the PA UI, not give them API keys |
| UiPath Cloud API Keys | OAuth2 client credentials / Personal Access Tokens (PATs) | Deprecated March 2025 per PITFALLS.md | Same — Phase 9 doesn't call UiPath API, but setup_guide.md should reference the current auth model |
| `croniter` Kiorky fork | `pallets-eco/croniter` | 2024 — donated to pallets-eco org | Same package name on PyPI; no import changes |
| Task Scheduler v1 XML | v1.3 schema (`version="1.3"` on `<Task>`) | Windows 10+ | Phase 9 targets `version="1.3"` — supports `CalendarTrigger` and modern elements |

**Deprecated/outdated:**
- `python` in Task Scheduler `<Command>` without full path — works on developer machines only; breaks under alternate user contexts. Always use `sys.executable` resolved at generation time.
- Nuget CLI (`nuget pack`) — unnecessary for UiPath; a `.nupkg` is just a zip with a `.nuspec`. Build with stdlib `zipfile`.

## Open Questions

1. **Exact PA non-solution flow package field minimums.**
   - What we know: Microsoft documents the user-facing export/import flow but not a hand-crafting spec. Community sources confirm `manifest.json` + `Microsoft.Flow/flows/{GUID}/definition.json` is the minimum shape.
   - What's unclear: Whether specific fields in `manifest.json` (`packageTelemetryId`, `hierarchy`, `configurableBy`) are strictly required or cosmetic. Whether PA rejects a zip with missing optional fields.
   - Recommendation: Wave 0 of plan 09-02 checks in a GOLDEN fixture — manually export a real minimal flow from an actual PA tenant, save as `tests/fixtures/pa_reference_flow.zip`. Use it as a structural reference for template rendering. Never commit real connection GUIDs.

2. **UiPath Studio-version compatibility for hand-crafted `project.json`.**
   - What we know: `schemaVersion` has been "4.0" for several years; Studio 23.10+ is the stable LTS.
   - What's unclear: Whether a stub `Main.xaml` that only contains `<WriteLine>` opens cleanly in modern UiPath Studio without triggering a forced migration dialog.
   - Recommendation: Accept this as a known limitation. Document in setup_guide.md: "The process package is a stub. Open in UiPath Studio 23.10+, add a Python Scope activity, republish." If Studio migration dialogs appear, user accepts and continues.

3. **Whether `ctx.tool_registry` lookup for MCP tool names is the right detection path for D-09.**
   - What we know: `WorkflowGenerateTool.__init__` takes `registry=workflow_registry`. `workflow_deploy` can take `tool_registry: ToolRegistry` too and look up `pa_deploy_flow` / `ui_deploy_process` by name.
   - What's unclear: Whether the `SessionContext` exposes `ctx.tool_registry` or whether it needs to be injected at tool construction time.
   - Recommendation: Inject via `__init__` like Phase 8 does with `WorkflowRegistry`. In `_register_workflow_tools`, pass the whole registry to `WorkflowDeployTool`. Plan 09-02 should verify this integration seam in Wave 0.

4. **Do we need a separate `template_engine.render_setup_guide()` method or is `render_text()` sufficient?**
   - What we know: `render_text()` is a generic non-Python template renderer with credential scanning.
   - What's unclear: Whether setup_guide.md needs any additional transforms (e.g., markdown escaping of user-controllable fields).
   - Recommendation: Use `render_text()` uniformly. If specific markdown escaping is needed, add a Jinja2 filter `{{ workflow_name | md_escape }}` inside the templates rather than a new method. Simpler.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | Everything | ✓ | 3.11.9 | — |
| jinja2 | All template rendering | ✓ | 3.1.6 | — |
| croniter | Schedule validation, overdue check | ✓ | 6.2.2 | — |
| filelock | Registry concurrency | ✓ | 3.25.2 | — |
| pydantic | Tool input schemas | ✓ | 2.12.5 | — |
| zipfile (stdlib) | PA/UiPath zip bundles | ✓ | n/a | — |
| Phase 8 `WorkflowRegistry` | All read/write to registry | ✓ | in-repo | — |
| Phase 8 `TemplateEngine` | All template rendering | ✓ | in-repo | — |
| Phase 8 `workflow_generate` (reference) | Implementation pattern for new tools | ✓ | in-repo | — |
| Real Power Automate tenant for ZIP import smoke test | Acceptance verification of `flow_import.zip` | ✗ | — | Use golden fixture + structural validation; document manual import test as phase gate |
| Real UiPath Orchestrator for .nupkg upload smoke test | Acceptance verification of `process_package.zip` | ✗ | — | Document stub limitation in setup_guide.md; manual verification is out of scope for unit tests |

**Missing dependencies with no fallback:** None — Phase 9 is pure code + file I/O; all runtime deps are already installed.

**Missing dependencies with fallback:** PA tenant and UiPath Orchestrator are external verification targets, not runtime dependencies. Planner should note that the guided-mode ZIP outputs cannot be unit-tested against a real platform; structural validation (zipfile member list + JSON schema shape + round-trip read of manifest/definition JSON) is the automated gate.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 + pytest-mock 3.15.1 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options] testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_manage.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEP-01 | `workflow_deploy local` emits task_scheduler.xml + crontab.txt + setup_guide.md into `local_guided/` subfolder | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_local_mode_emits_all_artifacts -x` | ❌ Wave 0 |
| DEP-01 | Generated task_scheduler.xml parses as valid XML and contains absolute python path | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_task_scheduler_xml_shape -x` | ❌ Wave 0 |
| DEP-01 | Generated crontab.txt has PATH line, cd + python command, trailing newline | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_crontab_txt_shape -x` | ❌ Wave 0 |
| DEP-01 | Cron-to-TaskScheduler dispatcher handles daily/monthly/weekly/every-N-hours | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_cron_to_taskscheduler -x` | ❌ Wave 0 |
| DEP-02 | `workflow_deploy guided target=power_automate` emits setup_guide.md, flow_import.zip, task_scheduler.xml, test_trigger.ps1 | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_guided_pa_emits_bundle -x` | ❌ Wave 0 |
| DEP-02 | flow_import.zip contains manifest.json + `Microsoft.Flow/flows/{GUID}/definition.json` with forward-slash paths | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_pa_zip_structure -x` | ❌ Wave 0 |
| DEP-02 | `workflow_deploy guided target=uipath` emits process_package.zip with project.json, Main.xaml, nuspec | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_guided_uipath_emits_bundle -x` | ❌ Wave 0 |
| DEP-02 | setup_guide.md contains no plaintext credentials (credential scanner green) | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_setup_guide_credential_scan -x` | ❌ Wave 0 |
| DEP-02 | SSTI payload in workflow_name does NOT execute in any generated artifact | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_ssti_blocked_across_templates -x` | ❌ Wave 0 |
| DEP-03 | `workflow_deploy auto` returns structured next_steps payload when MCP tool present | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_auto_mode_returns_next_steps -x` | ❌ Wave 0 |
| DEP-03 | `workflow_deploy auto` returns error with hint when MCP tool missing | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_auto_mode_missing_mcp_error -x` | ❌ Wave 0 |
| DEP-04 | `target="local"` with `deploy_mode != "local"` returns clear error | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_local_target_requires_local_mode -x` | ❌ Wave 0 |
| DEP-05 | After any deploy, registry.json entry has target/deploy_mode/schedule/last_deployed/deploy_id populated | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_deploy_writes_registry_metadata -x` | ❌ Wave 0 |
| DEP-05 | Manifest per-version entry has deployed_to/deploy_mode/deploy_id/status after deploy | unit | `pytest tests/test_tools/test_workflow_deploy.py::test_deploy_writes_manifest_metadata -x` | ❌ Wave 0 |
| LCM-01 | `list` shows all workflows; hides retired by default; shows retired when include_retired=True | unit | `pytest tests/test_tools/test_workflow_manage.py::test_list_action -x` | ❌ Wave 0 |
| LCM-01 | `list` reads Phase 8 entries (missing Phase 9 fields) without KeyError | unit | `pytest tests/test_tools/test_workflow_manage.py::test_list_lazy_defaults_phase8_entry -x` | ❌ Wave 0 |
| LCM-02 | `inspect` returns full manifest + lazy-default fields | unit | `pytest tests/test_tools/test_workflow_manage.py::test_inspect_action -x` | ❌ Wave 0 |
| LCM-03 | `pause` flips status to "paused" in registry.json only; returns instructional next_step | unit | `pytest tests/test_tools/test_workflow_manage.py::test_pause_action -x` | ❌ Wave 0 |
| LCM-03 | `resume` flips paused → active | unit | `pytest tests/test_tools/test_workflow_manage.py::test_resume_action -x` | ❌ Wave 0 |
| LCM-04 | `rollback` requires target_version; flips manifest active↔superseded; updates current_version | unit | `pytest tests/test_tools/test_workflow_manage.py::test_rollback_action -x` | ❌ Wave 0 |
| LCM-04 | `rollback` returns instructional next_step including exact deploy call | unit | `pytest tests/test_tools/test_workflow_manage.py::test_rollback_next_step -x` | ❌ Wave 0 |
| LCM-05 | `retire` flips status to retired in registry and manifest; list hides it | unit | `pytest tests/test_tools/test_workflow_manage.py::test_retire_action -x` | ❌ Wave 0 |
| LCM-05 | After retire, re-running `workflow_generate` with same name creates new version alongside | integration | `pytest tests/test_tools/test_workflow_manage.py::test_retire_then_regenerate -x` | ❌ Wave 0 |
| LCM-06 | `health_check` flags overdue via croniter `get_prev > last_run` for active workflows only | unit | `pytest tests/test_tools/test_workflow_manage.py::test_health_check_overdue -x` | ❌ Wave 0 |
| LCM-06 | `health_check` skips paused workflows in overdue calc | unit | `pytest tests/test_tools/test_workflow_manage.py::test_health_check_skips_paused -x` | ❌ Wave 0 |
| LCM-06 | `health_check` returns null failure_rate_pct when run_count_30d == 0 | unit | `pytest tests/test_tools/test_workflow_manage.py::test_health_check_null_failure_rate -x` | ❌ Wave 0 |
| LCM-06 | `health_check` does NOT flag just-deployed workflows as overdue | unit | `pytest tests/test_tools/test_workflow_manage.py::test_health_check_fresh_deploy_not_overdue -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_tools/test_workflow_deploy.py tests/test_tools/test_workflow_manage.py -x` (fast — no I/O beyond tmp_path)
- **Per wave merge:** `pytest tests/test_tools/ -x` (~5s; covers all tool tests)
- **Phase gate:** `pytest tests/ -x` (full suite green before `/gsd:verify-work`)

### Wave 0 Gaps

- [ ] `tests/test_tools/test_workflow_deploy.py` — new file; covers all DEP-01..05
- [ ] `tests/test_tools/test_workflow_manage.py` — new file; covers all LCM-01..06
- [ ] `tests/fixtures/pa_reference_flow.zip` (optional) — golden fixture for structural comparison, extracted from a real PA export. If not available, tests use structural assertions (JSON schema shape + zipfile member list).
- [ ] `tests/test_tools/test_workflow_templates.py` — EXTEND existing file with new tests for `render_text()` method and each new non-Python template
- [ ] Shared fixture for a Phase 8 registry state (no Phase 9 fields) to verify lazy-default reads — add to `tests/conftest.py` or a new `tests/test_tools/conftest.py`

## Sources

### Primary (HIGH confidence)
- Phase 8 source code — `yigthinker/tools/workflow/registry.py`, `template_engine.py`, `workflow_generate.py` (in-repo, most recent Phase 8 commits)
- Phase 8 test suite — `tests/test_tools/test_workflow_templates.py`, `test_workflow_registry.py`, `test_workflow_generate.py`
- `.planning/phases/08-workflow-foundation/08-CONTEXT.md` — Phase 8 locked decisions
- `.planning/phases/09-deployment-lifecycle/09-CONTEXT.md` — Phase 9 locked decisions
- `.planning/research/PITFALLS.md` — Phase 8/9 shared pitfall catalog (credential leakage, registry corruption, Task Scheduler env, Windows schtasks path issues)
- `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md` Sections 4.2, 4.3, 5, 12.1–12.3
- Microsoft Learn — Task Scheduler XML schema: https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema
- Microsoft Learn — Task Scheduler Time Trigger example: https://learn.microsoft.com/en-us/windows/win32/taskschd/time-trigger-example--xml-
- Microsoft Learn — Daily/Weekly trigger examples: https://learn.microsoft.com/en-us/windows/win32/taskschd/daily-trigger-example--xml-
- Microsoft Learn — schtasks.exe reference: https://learn.microsoft.com/en-us/windows/win32/taskschd/schtasks
- Microsoft Learn — PA non-solution export/import: https://learn.microsoft.com/en-us/power-automate/export-import-flow-non-solution
- PyPI — croniter 6.2.2 (published 2026-03-15): https://pypi.org/project/croniter/
- croniter GitHub — pallets-eco/croniter: https://github.com/pallets-eco/croniter
- UiPath Studio — project.json docs: https://docs.uipath.com/studio/standalone/2024.10/user-guide/about-the-projectjson-file
- UiPath OrchestratorManager real project.json: https://github.com/UiPath/OrchestratorManager/blob/master/project.json

### Secondary (MEDIUM confidence)
- "Editing Power Automate Export Packages" blog post (2025-10-03): https://edvaldoguimaraes.com.br/2025/10/03/editing-power-automate-export-packages/ — source for manifest.json / definition.json structural description
- "Understanding the Power Automate Definition" (DEV Community): https://dev.to/wyattdave/understanding-the-power-automate-definition-42po
- Python stdlib `zipfile` docs (implicit via ClaudeMD "python 3.11 stdlib")

### Tertiary (LOW confidence — flag for validation)
- Exact field requirements of PA `manifest.json` — community sources describe structure but Microsoft does not publish a hand-crafting schema. **Validation path:** golden fixture from real PA export + first-import smoke test during Phase 9 acceptance.
- UiPath .nupkg stub XAML — documented stub pattern, but whether modern Studio 23.10+ opens the stub without migration warnings is untested. **Validation path:** document limitation in setup_guide.md; accept user friction.
- Windows Task Scheduler XML `encoding="UTF-16"` requirement — some docs say "Task Scheduler stores as UTF-16" but `schtasks /create /xml` also accepts UTF-8. **Validation path:** Phase 9 generates UTF-8; add a comment in the template; test on Windows during acceptance.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all deps already installed and Phase 8 verified
- Architecture patterns (lazy-default reads, in-memory zip, cron dispatcher): HIGH — each pattern derives directly from Phase 8 code or stdlib
- Task Scheduler XML structure: HIGH — Microsoft official examples
- Crontab format: HIGH — well-documented POSIX standard
- Registry schema extension: HIGH — one-field-at-a-time additive; Phase 8 `save_index` merge is already defensive
- Cron → Task Scheduler conversion: MEDIUM — no library exists; dispatcher handles the four canonical shapes and falls back gracefully. Edge cases may need iteration during implementation.
- PA flow_import.zip structure: MEDIUM — community-sourced; requires golden fixture + real-import smoke test at phase gate
- UiPath .nupkg stub: MEDIUM — documented project.json schema; stub Main.xaml is an acknowledged limitation
- Pitfalls: HIGH — inherited from Phase 8 research + explicit new items for health_check edge cases and rollback race

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (30 days for stable libraries; Task Scheduler and cron formats are stable for decades; PA/UiPath guided-mode artifacts should be re-verified if MS/UiPath changes their import formats)
