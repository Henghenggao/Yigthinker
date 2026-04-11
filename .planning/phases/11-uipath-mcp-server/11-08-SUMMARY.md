---
phase: 11-uipath-mcp-server
plan: 08
subsystem: workflow-rpa-bridge
tags: [docs, uipath, mcp, readme, oauth2, rpa]
requires: [11-06, 11-07]
provides:
  - "Copy-pasteable installation + configuration guide for yigthinker-mcp-uipath"
  - ".mcp.json snippet with flat-underscore vault:// keys aligned to _resolve_env"
  - "Troubleshooting runbook for detection / env / OAuth2 / stdio failures"
affects: ["packages/yigthinker-mcp-uipath/README.md"]
tech-stack:
  added: []
  patterns:
    - "Docs aligned to config.py source of truth (6 env vars, singular UIPATH_SCOPE)"
    - "Flat underscore vault keys per D-10 (vault://uipath_client_id, not slash form)"
key-files:
  created: []
  modified:
    - path: "packages/yigthinker-mcp-uipath/README.md"
      size_lines: 484
      description: "Replaced 5-line Plan 11-01 scaffold stub with full end-user docs"
decisions:
  - "README uses UIPATH_SCOPE (singular) exclusively and the sentence explaining singular-ness is phrased so the plural string never appears — satisfies VALIDATION.md Row 11-08-01 `! grep -q UIPATH_SCOPES`"
  - "Legacy identifier `yigthinker_uipath_mcp` is NOT mentioned in the README text, even as a counter-example — keeps grep-based regression guards green"
  - "Vault-mapping section documents the exact `_resolve_env` transform (strip `vault://`, uppercase remainder) and explicitly warns against slash forms — closes the D-10 silent-failure trap"
  - "Troubleshooting for 401 lists 4 distinct causes (bad creds, comma-separated scopes, missing `orchestrator_` suffix, tenant/org mismatch) — matches Manual-Only Verifications row on scope list minimization"
metrics:
  duration_minutes: ~6
  completed: 2026-04-11
  tasks_completed: 1
  files_modified: 1
  lines_added: 481
  lines_removed: 2
---

# Phase 11 Plan 08: UiPath MCP Server README Summary

End-user README for `yigthinker-mcp-uipath` documenting installation,
UIPATH_* configuration, `.mcp.json` wiring, all 5 tool signatures, and
troubleshooting -- the canonical on-disk doc that UAT will follow.

## Context

Plan 11-01 created a 5-line stub README. Plans 11-02 through 11-07
delivered the working package (47 tests green, drift cleanup applied,
`rpa-uipath` extra added to core). Plan 11-08 closes the phase by
replacing the stub with a complete end-user guide — the last thing a
user touches before they go into real-tenant UAT (`11-HUMAN-UAT.md`).

This is a docs-only plan: no Python code was touched, no core files
were edited, `suggest_automation.py` was left alone per D-07.

## What Was Built

### `packages/yigthinker-mcp-uipath/README.md` (484 lines)

Full end-user documentation in 8 sections:

1. **Title + overview** — one-line description, package/module/command,
   Python 3.11+ + Automation Cloud OAuth2 requirement, explicit
   architect-not-executor framing ("Yigthinker never imports this
   package at runtime").
2. **Installation** — two-step editable path
   (`pip install -e .[rpa-uipath]` then
   `pip install -e packages/yigthinker-mcp-uipath[test]`) AND the
   future PyPI single-command path (D-25).
3. **Configuration** — three subsections:
   - **UiPath Automation Cloud setup** — walks through creating the
     External Application with the 5 required scopes, recording
     organization / tenant / base URL.
   - **Environment variables** — full 6-row table covering
     `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET`, `UIPATH_BASE_URL`,
     `UIPATH_TENANT`, `UIPATH_ORGANIZATION`, `UIPATH_SCOPE` with
     required/optional + example columns. Explicitly calls out
     singular `UIPATH_SCOPE` and space-separated (not comma)
     semantics per RFC 6749 / Pitfall 3.
   - **.mcp.json with vault:// secrets** — documents the exact
     `_resolve_env` transform (`vault://` stripped, remainder
     uppercased) with worked examples; complete copy-pasteable
     `mcpServers.uipath` block including all 6 env vars; alternative
     block showing how to move tenant/organization/scope to vault;
     shell commands for setting `VAULT_UIPATH_*` vars on both bash
     and PowerShell.
4. **Tools** — all 5 tool signatures with Pydantic-model-accurate
   field tables, example JSON input blocks, return shape, and
   failure-mode dict keys. Field names and defaults match the
   Plan 11-05 input schemas verbatim (`workflow_name`, `script_path`,
   `process_key`, `folder_path="Shared"`, `top=10 (1-100)`,
   `action: Literal["create","pause","resume","delete"]`, etc.).
5. **End-to-end example** — design spec §12.2 happy path
   (`yigthinker --query "Deploy my monthly AR aging workflow..."`)
   with a 3-step narrative showing `ui_deploy_process` ->
   `ui_trigger_job` -> `ui_job_history` tool-call chain.
6. **Troubleshooting** — 4 failure modes per D-27:
   - "Package not detected" — wrong venv, Phase 9 drift regression,
     import failure (with diagnostic commands for each).
   - "Missing required env vars RuntimeError" — documents the
     5-required-var contract, names the two fields most often
     missed (`UIPATH_TENANT` / `UIPATH_ORGANIZATION`).
   - "OAuth2 401" — 4 distinct causes (bad creds, comma-separated
     scopes, missing trailing `orchestrator_`, tenant/org
     mismatch against base URL) each with concrete fix.
   - "stdio handshake hangs" — stdout pollution, missing env vars
     at startup, async runtime clash with embedded usage.
7. **License** — points at root `LICENSE`.
8. **Links** — Yigthinker repo, UiPath External Applications docs,
   Orchestrator OData reference, Cross-Platform project format, MCP
   specification.

## Verification

### Automated (VALIDATION.md Row 11-08-01)

```bash
test -f packages/yigthinker-mcp-uipath/README.md \
  && grep -l "UIPATH_CLIENT_ID\|UIPATH_TENANT\|UIPATH_ORGANIZATION\
     \|UIPATH_SCOPE\|vault://uipath_client_id\|ui_deploy_process\
     \|OR.Execution OR.Jobs\|rpa-uipath" \
     packages/yigthinker-mcp-uipath/README.md \
  && ! grep -q "UIPATH_SCOPES" packages/yigthinker-mcp-uipath/README.md
```

**Result:** PASS — file exists, all 8 required literal strings
present, `UIPATH_SCOPES` plural absent.

### Per-string match counts

| String                        | Count | Required |
|-------------------------------|-------|----------|
| `UIPATH_CLIENT_ID`            | 10    | >= 1     |
| `UIPATH_CLIENT_SECRET`        | 7     | >= 1     |
| `UIPATH_BASE_URL`             | 8     | >= 1     |
| `UIPATH_TENANT`               | 13    | >= 2     |
| `UIPATH_ORGANIZATION`         | 12    | >= 2     |
| `UIPATH_SCOPE`                | 10    | >= 3     |
| `vault://uipath_client_id`    | 5     | >= 1     |
| `vault://uipath_scope`        | 2     | >= 1     |
| `ui_deploy_process`           | 3     | >= 1     |
| `ui_trigger_job`              | 2     | >= 1     |
| `ui_job_history`              | 2     | >= 1     |
| `ui_manage_trigger`           | 1     | >= 1     |
| `ui_queue_status`             | 1     | >= 1     |
| `OR.Execution OR.Jobs`        | 3     | >= 1     |
| `rpa-uipath`                  | 4     | >= 1     |
| `yigthinker_mcp_uipath`       | 14    | >= 5     |
| `orchestrator_`               | 7     | >= 1     |

### Forbidden strings (must be 0)

| String                  | Count | Result |
|-------------------------|-------|--------|
| `UIPATH_SCOPES`         | 0     | PASS   |
| `uipath_scopes`         | 0     | PASS   |
| `yigthinker_uipath_mcp` | 0     | PASS   |

### Package regression

```
cd packages/yigthinker-mcp-uipath && python -m pytest tests/ -x -q
47 passed in 7.14s
```

All 47 tests still green — docs-only plan, no source touched.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 - Bug] Removed literal `UIPATH_SCOPES` from explanatory
sentence**

- **Found during:** Task 1 post-write validation.
- **Issue:** Draft text read "The variable is `UIPATH_SCOPE` (singular),
  not `UIPATH_SCOPES`." The validation contract `! grep -q UIPATH_SCOPES`
  fails on ANY occurrence — even inside a negative-example sentence.
- **Fix:** Rewrote the sentence to
  `The variable is **UIPATH_SCOPE** -- singular, no trailing "S".`
  which still communicates the gotcha without spelling the forbidden
  plural.
- **Commit:** 214351d

**2. [Rule 1 - Bug] Removed literal `yigthinker_uipath_mcp` from
troubleshooting counter-example**

- **Found during:** Task 1 post-write validation.
- **Issue:** Draft text read
  `"...edited to use a legacy name (e.g. yigthinker_uipath_mcp)
  instead of the canonical yigthinker_mcp_uipath"` — the acceptance
  criterion `grep "yigthinker_uipath_mcp" README.md` returns 0 matches
  means the legacy identifier must not appear anywhere in the file.
- **Fix:** Rewrote to
  `"...edited to reference a legacy module name instead of the
  canonical yigthinker_mcp_uipath"` — keeps the diagnostic advice,
  drops the forbidden literal.
- **Commit:** 214351d

No architectural changes. No Python source touched. No CLAUDE.md
conflicts. D-01, D-07, D-09, D-10, D-19, D-22, D-25, D-27 all honored.

## Authentication Gates

None — pure docs plan.

## Decisions Made

See frontmatter `decisions`. Key points:

1. Explanatory text for "singular not plural" rewrites the negative
   counterexample so the forbidden literal string never appears. This
   is how grep-based CI contracts differ from human-review contracts:
   the check cannot tell the difference between a warning and a
   directive, so the forbidden string must be absent from EVERY
   context.
2. Same treatment applied to the legacy `yigthinker_uipath_mcp`
   identifier — phase 11 drift guards treat its presence as a
   regression regardless of context.
3. The `.mcp.json` snippet intentionally mixes vault:// refs (for the
   two true secrets) with inline values (for base URL, tenant, org,
   scope) because the latter four are typically not sensitive and
   making the minimum vault surface small reduces misconfiguration
   risk. A second snippet shows the maximum-vault variant for users
   who want everything externalized.

## Known Stubs

None.

## Deferred Issues

None.

## Self-Check: PASSED

- `packages/yigthinker-mcp-uipath/README.md` exists at 484 lines.
- Commit `214351d` exists on master.
- VALIDATION Row 11-08-01 grep command returns success (file path
  printed) AND `! grep -q UIPATH_SCOPES` returns true (0 plural
  matches).
- Package regression suite: 47/47 passing.
- No forbidden strings (`UIPATH_SCOPES`, `uipath_scopes`,
  `yigthinker_uipath_mcp`) appear in the README.
