# Phase 9: Deployment & Lifecycle - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers `workflow_deploy` (local/guided/auto modes) and `workflow_manage` (list/inspect/pause/resume/rollback/retire/health_check). It operates on the WorkflowRegistry built in Phase 8 — reading versioned artifacts and writing deployment metadata back. Phase 10 will populate `/api/rpa/report` data consumed by `health_check`; Phases 11-12 will stand up the MCP servers `auto` mode targets.

Phase 9 is Yigthinker's "architect, not executor" boundary made concrete: the tool returns artifacts, instructions, and structured next-step plans — it never ssh's, subprocess-execs, or calls MCP tools directly.

</domain>

<decisions>
## Implementation Decisions

### Local Deploy Mode (DEP-01)
- **D-01:** `local` mode always emits BOTH `task_scheduler.xml` (Windows) and `crontab.txt` (Linux/macOS) into the version directory's `local_guided/` subfolder. No platform branching, no `os` input parameter. The Yigthinker host OS is orthogonal to the deploy target OS, so always shipping both is the only correct default. User picks which to install.
- **D-02:** Local scheduler artifacts are rendered via Jinja2 from `templates/local/task_scheduler.xml.j2` and `templates/local/crontab.txt.j2`, consistent with the Phase 8 template pipeline (SandboxedEnvironment). Template variables come from the workflow manifest + `schedule` field + absolute path to `main.py`.
- **D-03:** Local mode also renders a `setup_guide.md` explaining how to install each artifact (`schtasks /create /xml ...` and `crontab crontab.txt`) so the LLM can paste it into IM.

### Guided Deploy Mode (DEP-02)
- **D-04:** `guided` mode produces a `{target}_guided/` subfolder inside the version directory with: `setup_guide.md`, `flow_import.zip` (PA) or `process_package.zip` (UiPath), `task_scheduler.xml`, `test_trigger.ps1`, and `crontab.txt`. Follows the design spec Section 4.2 layout.
- **D-05:** All artifacts are generated at runtime via Jinja2 templates. For `flow_import.zip` / `process_package.zip`, the tool renders the PA Flow definition JSON / UiPath project.json from `.j2` templates, then uses `zipfile.ZipFile(mode="w", compression=ZIP_DEFLATED)` to bundle them. No binary blobs checked into the repo.
- **D-06:** The minimal PA Flow is notification-only: "When an HTTP request is received" → "Send an email (V2)" (per design spec Section 4.2). The UiPath package is a Python activity wrapper stub. Both are intentionally minimal — complex orchestration stays in `main.py`.
- **D-07:** `setup_guide.md` is IM-native: numbered steps, triple-backtick code blocks, no HTML. Instructs the user through pip install → config.yaml fill-in → flow import → trigger URL copy → scheduler install → test run. Step numbering and content are parameterized per target (PA vs UiPath).

### Auto Deploy Mode (DEP-03)
- **D-08:** `auto` mode returns a structured `next_steps` payload to the LLM. Shape:
  ```python
  {
    "mode": "auto",
    "target": "power_automate" | "uipath",
    "artifacts_ready": {...file paths...},
    "next_steps": [
      {"tool": "pa_deploy_flow", "args": {...}},
      {"tool": "pa_trigger_flow", "args": {...}},
    ],
    "message": "Generated artifacts are ready. Call the listed MCP tools in order to deploy.",
  }
  ```
  The tool does NOT call MCP servers directly — the LLM sees the plan and calls through the normal AgentLoop cycle. Matches design spec "Yigthinker is architect, not executor".
- **D-09:** When `deploy_mode="auto"` is requested but no matching MCP server is registered in `ctx.tool_registry`, the tool returns an error with a hint to use `guided` mode instead. Detection is a simple lookup in the registry for `pa_deploy_flow` (PA) or `ui_deploy_process` (UiPath). No silent downgrade — the LLM decides whether to retry with mode=guided.

### Mode Auto-Selection (DEP-04)
- **D-10:** `deploy_mode` is a required input parameter. The LLM picks the mode based on environment (per design spec — MCP available → auto, PA/UiPath mentioned but no API → guided, no RPA → local). The tool itself does no auto-detection beyond the MCP-missing error in D-09. This keeps the tool deterministic and the LLM in control of the policy.

### Registry Schema Extension (DEP-05)
- **D-11:** Phase 9 adds these fields to `registry.json` workflow entries (on top of Phase 8's shape): `target`, `deploy_mode`, `schedule`, `last_deployed`, `last_run`, `last_run_status`, `failure_count_30d`, `run_count_30d`, `deploy_id`. `current_version` field is added as a pointer (separate from Phase 8's `latest_version` which tracks the highest version number; `current_version` is the active/deployed one, which rollback can flip backward).
- **D-12:** Manifest per-version entries add: `deployed_to`, `deploy_mode`, `deploy_id`, `status` (`"active"` | `"superseded"` | `"retired"`).
- **D-13:** Schema extension is lazy-default on read: `WorkflowRegistry.load_index()` and `get_manifest()` fill missing fields with `None` or sensible defaults. First write from Phase 9 upgrades the entry. No explicit migration pass, no `schema_version` field yet. Phase 8 entries keep working untouched until deploy touches them.
- **D-14:** After any `workflow_deploy` call (local, guided, or auto), the tool writes metadata back via `WorkflowRegistry.save_index()` and `save_manifest()` under the existing filelock contract from Phase 8.

### Pause/Resume (LCM-03)
- **D-15:** Pause/resume flip the registry-level `status` field ONLY (`"active"` ↔ `"paused"`). Yigthinker does not subprocess-exec `schtasks` or call MCP tools. Instead, `workflow_manage` returns an instructional next-step block telling the user how to disable their scheduler (`schtasks /change /tn <name> /disable` for local, pa_pause_flow next-step for auto PA, ui_manage_trigger next-step for auto UiPath). The LLM can execute those MCP next-steps through the normal AgentLoop if the user wants full automation.
- **D-16:** A paused workflow is skipped by `health_check` overdue calculation (paused workflows can't be overdue).

### Rollback (LCM-04)
- **D-17:** Rollback is a two-step operation: (1) flip manifest — current version `"active"` → `"superseded"`, target version `"superseded"` → `"active"`; update `registry.json` `current_version` pointer. (2) Return instructional next-step: "Run `workflow_deploy` with `workflow_name=X, target_version=vN` to push the rolled-back artifacts to your scheduler/RPA."
- **D-18:** The registry flip itself is transactional (under filelock). Re-deploy is explicit and separate. This keeps rollback cheap and auditable; mixed-target/mode rollbacks (v2 was `auto PA`, v1 was `guided PA`) are handled by the follow-up deploy call using whatever mode the user/LLM picks.
- **D-19:** `target_version` input is required for rollback; no implicit "previous version" default — explicit is safer.

### Retire (LCM-05)
- **D-20:** Retire flips `status="retired"` in both registry.json entry and the currently-active version's manifest. Files are preserved. Retire is one-way from a UI perspective (list hides retired by default), but reversible via an explicit `workflow_manage reactivate` — OUT OF SCOPE for Phase 9 (not in requirements). Re-running `workflow_generate` with the same name creates a new v(N+1) alongside the retired entry.

### Health Check (LCM-06)
- **D-21:** `health_check` computes whatever data is available in Phase 9:
  - Overdue: `croniter(schedule).get_prev(datetime, now) > last_run` → flag as overdue (only for `status="active"` workflows).
  - Failure rate: only computed if `run_count_30d > 0`; else reported as `null`.
  - Run counts default to 0 on missing data; returned as-is.
- **D-22:** Return shape is a structured list: `[{name, status, schedule, last_run, overdue: bool, failure_rate_pct: float | null, alerts: [str]}]`. Empty fields are expected until Phase 10 populates them via `/api/rpa/report` — documented as a known limitation in the tool description.

### Tool Input Design
- **D-23:** `workflow_deploy` input schema:
  ```python
  class WorkflowDeployInput(BaseModel):
      workflow_name: str
      version: int | None = None  # default: current_version from registry
      target: Literal["local", "power_automate", "uipath"]
      deploy_mode: Literal["auto", "guided", "local"]
      schedule: str | None = None  # cron expression, validated via croniter
      credentials: dict[str, str] = {}  # vault:// refs only
      notify_on_complete: str | None = None
  ```
  Note: when `target="local"`, `deploy_mode` must be `"local"` (enforced in tool). Invalid combinations return a clear error.
- **D-24:** `workflow_manage` input schema matches design spec Section 4.3 exactly:
  ```python
  class WorkflowManageInput(BaseModel):
      action: Literal["list", "inspect", "pause", "resume", "rollback", "retire", "health_check"]
      workflow_name: str | None = None  # required for inspect/pause/resume/rollback/retire
      target_version: int | None = None  # required for rollback
  ```

### Plan Structure
- **D-25:** Phase 9 splits into 3 plans:
  - **09-01** (Wave 1, foundation): Registry schema extension (lazy defaults on Phase 8 registry) + local mode templates (task_scheduler.xml, crontab.txt, setup_guide.md) + `workflow_deploy` shell with local mode working end-to-end. This plan carries the registry contract that later plans depend on.
  - **09-02** (Wave 2, depends on 09-01): `workflow_deploy` guided + auto modes. Guided mode's `flow_import.zip` builder + PA/UiPath setup_guide.md templates. Auto mode's structured next-step payload + MCP-missing error path.
  - **09-03** (Wave 2, independent of 09-02, runs in parallel): `workflow_manage` — all 7 actions. Uses the extended registry contract from 09-01. Health check uses croniter (already a Phase 8 dependency).

### Claude's Discretion
- **D-26:** Exact template variable naming and sub-template structure for guided mode are at the planner's discretion, following Phase 8's Jinja2 inheritance precedent where it fits.
- **D-27:** Exact output format for `list`/`inspect`/`health_check` (JSON structure vs. tabular markdown) is at planner discretion — LLM-friendly structured dicts are the default, but a short rendered summary in the `content` field alongside structured data is acceptable.
- **D-28:** `deploy_id` semantics (GUID, hash, timestamp) is at planner discretion — recommend `{workflow_name}-v{n}-{deploy_mode}-{timestamp}` for debuggability.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design Spec
- `docs/superpowers/specs/2026-04-09-workflow-rpa-bridge-design.md` Section 4.2 (`workflow_deploy`, lines 107-238), Section 4.3 (`workflow_manage`, lines 240-257), Section 5 (Registry schema, lines 259-364), Section 12.1-12.3 (end-to-end deploy scenarios, lines ~700-850)

### Research (shared with Phase 8)
- `.planning/research/ARCHITECTURE.md` — Integration points, build order
- `.planning/research/PITFALLS.md` — SSTI, credential leakage, registry corruption
- `.planning/research/SUMMARY.md` — Synthesized findings

### Phase 8 Artifacts (direct dependencies)
- `yigthinker/tools/workflow/registry.py` — `WorkflowRegistry` class — Phase 9 extends its schema (D-11/D-12/D-13) via lazy-default reads, no method signature changes
- `yigthinker/tools/workflow/template_engine.py` — `TemplateEngine` with `SandboxedEnvironment` + AST validation — Phase 9 adds new template render methods (`render_local_scheduler`, `render_guided_bundle`, etc.)
- `yigthinker/tools/workflow/workflow_generate.py` — Reference implementation pattern for new tools
- `yigthinker/tools/workflow/templates/` — Phase 9 adds `local/`, extends `power_automate/`, `uipath/` subfolders
- `.planning/phases/08-workflow-foundation/08-CONTEXT.md` — Phase 8 decisions D-01 through D-16

### Existing Code Patterns
- `yigthinker/tools/base.py` — YigthinkerTool Protocol
- `yigthinker/registry_factory.py` — `_register_workflow_tools(registry, workflow_registry)` — extend to register `workflow_deploy` and `workflow_manage` under the same feature gate
- `yigthinker/builder.py` — `gate("workflow", settings=settings)` — already gates workflow subsystem; Phase 9 reuses the same gate
- `yigthinker/tools/reports/report_generate.py` — File-writing tool pattern (closest reference for artifact-producing tools)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WorkflowRegistry` (Phase 8) — already handles versioned storage, filelock, atomic writes. Phase 9 tools call `load_index`, `save_index`, `get_manifest`, `save_manifest` directly. No new low-level I/O code.
- `TemplateEngine` (Phase 8) — `SandboxedEnvironment` + AST validation + credential scanner. Phase 9 adds new render methods that reuse the same Jinja2 environment and validation helpers.
- `croniter` — already a Phase 8 dependency; used for `health_check` overdue calculation in LCM-06.
- `zipfile` — Python stdlib, used in guided mode to bundle `flow_import.zip` and `process_package.zip`.
- `feature gate("workflow")` — already registered in Phase 8's builder.py; both new tools register under the same gate.
- `_register_workflow_tools()` helper in registry_factory.py — extend to register `workflow_deploy` and `workflow_manage` alongside `workflow_generate`.

### Established Patterns
- **Tool registration:** Import tool class, call `registry.register(Tool(workflow_registry))`. Follows `workflow_generate` precedent.
- **Tool input:** Pydantic BaseModel with `Literal` for enums, optional fields defaulting to `None`.
- **Error handling:** Wrap `execute()` body in try/except, return `ToolResult(is_error=True, content=str(exc))`.
- **File I/O:** Tools that produce files write to `~/.yigthinker/workflows/{name}/v{n}/` via the registry — never directly.
- **Registry writes:** Always via `WorkflowRegistry` methods (which own the filelock). Never touch registry.json or manifest.json files directly from tool code.
- **`from __future__ import annotations`** in every source file.

### Integration Points
- `yigthinker/registry_factory.py::_register_workflow_tools` — add `WorkflowDeployTool` and `WorkflowManageTool` registrations
- `yigthinker/tools/workflow/workflow_deploy.py` — new file (new tool)
- `yigthinker/tools/workflow/workflow_manage.py` — new file (new tool)
- `yigthinker/tools/workflow/templates/local/` — new directory (task_scheduler.xml.j2, crontab.txt.j2, setup_guide.md.j2)
- `yigthinker/tools/workflow/templates/power_automate/` — extend with guided-mode templates (flow_import.json.j2, setup_guide.md.j2, test_trigger.ps1.j2)
- `yigthinker/tools/workflow/templates/uipath/` — extend with guided-mode templates (project.json.j2, setup_guide.md.j2, test_trigger.ps1.j2)
- `yigthinker/tools/workflow/registry.py` — lazy-default fills in load_index/get_manifest (minimal edits; D-13)
- `yigthinker/tools/workflow/template_engine.py` — new render methods (`render_local_scheduler`, `render_guided_bundle`, `render_setup_guide`); reuses same `SandboxedEnvironment`
- `pyproject.toml` — no new dependencies (croniter + jinja2 already from Phase 8)

</code_context>

<specifics>
## Specific Ideas

- Guided mode's PA Flow is deliberately minimal (HTTP trigger → send email). The design spec's Section 4.2 example is the reference — don't try to encode analysis logic in the PA Flow itself; that lives in `main.py`.
- `task_scheduler.xml` template should use `<Exec><Command>python</Command><Arguments>main.py</Arguments><WorkingDirectory>{absolute path}</WorkingDirectory></Exec>` with cron-to-Windows-schedule conversion for the `<Triggers>` section. Croniter can compute the Windows trigger spec via its `get_next` iterator.
- `workflow_deploy` must validate the schedule via croniter before writing any artifacts — fail-fast per D-16 of Phase 8.
- `workflow_manage list` should hide retired workflows by default; add an `include_retired: bool` input (optional, default False) so users can inspect them if needed. Consistent with "retire preserves files".
- Rollback instructional next-step should include the exact `workflow_deploy` call the LLM should issue next, with args pre-filled from the rolled-back manifest.
- `health_check` returns structured data + a human-readable `alerts` array. LLM can render the alerts directly in IM without additional formatting.
- All new templates go through `TemplateEngine`'s `SandboxedEnvironment` — no direct `jinja2.Template(...)` calls. This keeps Phase 8's SSTI protection in force.

</specifics>

<deferred>
## Deferred Ideas

- **`workflow_manage reactivate`** — Reverse of retire. Not in LCM requirements. Defer unless user asks.
- **Mode auto-detection inside the tool** — Design spec delegates mode selection to the LLM. Tool stays deterministic. Defer any auto-detect heuristics.
- **Registry schema_version field + explicit migration** — Overkill for a one-field extension. Revisit if schema changes accumulate across future phases.
- **Auto re-deploy on rollback** — Hides state changes. Keep rollback as two-step (flip + explicit deploy).
- **Subprocess-based pause (schtasks /change)** — Violates "architect not executor" for local mode. LLM + user handle scheduler control.
- **Run history stored locally by workflow_manage** — All run data comes from Phase 10's `/api/rpa/report`. Phase 9 does not write to `run_count_30d`, `failure_count_30d`, `last_run`, etc. — only reads.

</deferred>

---

*Phase: 09-deployment-lifecycle*
*Context gathered: 2026-04-10*
