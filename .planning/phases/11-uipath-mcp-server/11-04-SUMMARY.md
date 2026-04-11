---
phase: 11-uipath-mcp-server
plan: 04
subsystem: uipath-mcp-package
tags: [nupkg, packaging, uipath, cross-platform, zipfile, wave-1]
wave: 1
requirements: [MCP-UI-01]
one_liner: "Pure-function build_nupkg producing a valid 7-entry UiPath Cross-Platform Python .nupkg in-memory via stdlib zipfile, with operate.json (NOT project.json) per RESEARCH.md Finding 4"
dependency_graph:
  requires:
    - phase: 11-uipath-mcp-server
      provides: "Plan 11-01 nupkg.py stub + editable-install packaging"
  provides:
    - "build_nupkg(script_path: Path, workflow_name: str, version: str) -> bytes"
    - "4 verbatim UiPath SDK cli_pack.py string templates (_CONTENT_TYPES, _RELS_TPL, _NUSPEC_TPL, _PSMDCP_TPL)"
    - "operate.json + entry-points.json schemas hard-locked at cloud.uipath.com/draft/2024-12/entry-point"
    - "7 structural unit tests (test_nupkg.py) including Pitfall 6 regression guard"
  affects:
    - "Plan 11-05 ui_deploy_process handler — consumes build_nupkg output as upload bytes"
tech_stack:
  added: []
  patterns:
    - "Pure function: reads script_path once, no disk I/O for output (D-17 invariant)"
    - "string.Template-based XML generation — verbatim UiPath SDK templates, no hand-written NuGet XML"
    - "zipfile.ZipFile + io.BytesIO for in-memory .nupkg construction"
    - "ZIP_DEFLATED (Finding 4 — NOT ZIP_STORED)"
    - "UTF-8 BOM (\\ufeff) on nuspec to satisfy NuGet parser (Pitfall 5)"
    - "16-hex-char psmdcp filename via uuid.uuid4().hex[:16] (Finding 4)"
key_files:
  created:
    - "packages/yigthinker-mcp-uipath/tests/test_nupkg.py (7 tests, 112 lines)"
  modified:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/nupkg.py (stub → 152 lines, +149/-3)"
key_decisions:
  - "D-16 CORRECTED: content/operate.json (NOT content/project.json). D-16 literal wording was a drift from the authoritative UiPath Python SDK cli_pack.py — RESEARCH.md Finding 4 verified the correction against raw.githubusercontent.com/UiPath/uipath-python. We follow Finding 4, not D-16 wording."
  - "MVP drops content/package-descriptor.json and content/bindings_v2.json — Orchestrator MAY require the former. If UAT rejects, add per Finding 4 caveat."
  - "Pitfall 6 (project.json regression) guarded at TWO layers: grep-clean nupkg.py AND explicit `assert \"content/project.json\" not in names` in test_nupkg_has_required_files."
  - "authors = creator = \"yigthinker\" (lowercase, matches package pip name). Hard-coded, not parameterized — MVP scope."
  - "projectId and entrypoint uniqueId are fresh uuid4 per call — tests assert presence, not values."
patterns_established:
  - "RESEARCH.md > CONTEXT.md when findings correct a decision — the research note at D-16 is authoritative"
  - "Verbatim template copy from upstream SDKs when the format is schema-locked (avoid hand-written NuGet XML)"
  - "Pure-function invariant for .nupkg builder — caller owns disk I/O, builder is deterministic-modulo-UUIDs"
requirements_completed: [MCP-UI-01]
duration: ~2.5min
completed: 2026-04-11
---

# Phase 11 Plan 04: build_nupkg Pure Function Summary

**In-memory UiPath Cross-Platform Python .nupkg builder using stdlib zipfile + verbatim UiPath SDK templates, with operate.json (correcting D-16's project.json wording) and the mandatory Pitfall 6 regression guard.**

## Performance

- **Duration:** ~2.5 min (144 seconds)
- **Started:** 2026-04-11T19:22:40Z
- **Completed:** 2026-04-11T19:25:04Z
- **Tasks:** 2/2 completed (both TDD)
- **Files modified:** 2 (1 created, 1 overwritten-from-stub)

## Accomplishments

### Task 1 — RED (commit `8a48a8f`)

Created `packages/yigthinker-mcp-uipath/tests/test_nupkg.py` with 7 structural tests:

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_nupkg_has_required_files` | All 7 entries present; `content/project.json` NOT in names (Pitfall 6 guard); exactly 1 `.psmdcp` under `package/services/metadata/core-properties/` |
| 2 | `test_nuspec_contains_package_metadata` | `<id>test_flow</id>` and `<version>1.2.3</version>` in nuspec (decoded UTF-8-SIG) |
| 3 | `test_main_py_content_preserved` | `content/Main.py` equals source script byte-for-byte |
| 4 | `test_operate_json_targets_python_runtime` | `targetFramework=Portable`, `targetRuntime=python`, `contentType=Process`, `main=Main.py`, `runtimeOptions.requiresUserInteraction=False`, `runtimeOptions.isAttended=False`, `$schema=https://cloud.uipath.com/draft/2024-12/entry-point` |
| 5 | `test_entry_points_json_lists_main` | Single entry; `filePath=Main.py`; `type=process`; `uniqueId` present; `input.type=object` |
| 6 | `test_psmdcp_filename_is_16_hex_chars` | Basename matches `^[0-9a-f]{16}\.psmdcp$` |
| 7 | `test_pure_function_no_disk_write` | Returns bytes; `tmp_path` contents unchanged after call |

**RED state confirmed:** `ImportError: cannot import name 'build_nupkg' from 'yigthinker_mcp_uipath.nupkg'`.

### Task 2 — GREEN (commit `c4c24b1`)

Replaced the 6-line `nupkg.py` stub with a 152-line implementation:

- **4 verbatim templates** copied from `raw.githubusercontent.com/UiPath/uipath-python/main/packages/uipath/src/uipath/_cli/_templates/*` via RESEARCH.md Finding 4:
  - `_CONTENT_TYPES` — literal `<Types>` XML with 6 `<Default>` extensions (`rels`, `psmdcp`, `json`, `py`, `txt`, `nuspec`)
  - `_RELS_TPL` — `string.Template` with `$nuspecPath`, `$nuspecId`, `$psmdcpPath`, `$psmdcpId` placeholders
  - `_NUSPEC_TPL` — `string.Template` starting with `\ufeff` UTF-8 BOM (Pitfall 5), with `$packageName`, `$packageVersion`, `$authors`, `$description` placeholders
  - `_PSMDCP_TPL` — `string.Template` with `$creator`, `$description`, `$projectName`, `$packageVersion`, `$publicKeyToken` placeholders

- **`build_nupkg(script_path, workflow_name, version) -> bytes`**:
  1. Reads `script_path` via `read_text(encoding="utf-8")` — single disk read, no writes
  2. Generates fresh `uuid4` values for `project_id`, `entrypoint_id`, psmdcp path, rels IDs, and psmdcp publicKeyToken
  3. Substitutes all four templates
  4. Builds `operate_json` dict (7 keys at root: `$schema`, `projectId`, `main`, `contentType=Process`, `targetFramework=Portable`, `targetRuntime=python`, `runtimeOptions`)
  5. Builds `entry_points_json` dict with single entry point
  6. Writes 7 entries into `io.BytesIO` + `zipfile.ZipFile(..., ZIP_DEFLATED)` and returns `buf.getvalue()`

## Verification

```bash
cd packages/yigthinker-mcp-uipath && python -m pytest tests/test_nupkg.py -v
```

```
tests/test_nupkg.py::test_nupkg_has_required_files PASSED                [ 14%]
tests/test_nupkg.py::test_nuspec_contains_package_metadata PASSED        [ 28%]
tests/test_nupkg.py::test_main_py_content_preserved PASSED               [ 42%]
tests/test_nupkg.py::test_operate_json_targets_python_runtime PASSED     [ 57%]
tests/test_nupkg.py::test_entry_points_json_lists_main PASSED            [ 71%]
tests/test_nupkg.py::test_psmdcp_filename_is_16_hex_chars PASSED         [ 85%]
tests/test_nupkg.py::test_pure_function_no_disk_write PASSED             [100%]
============================== 7 passed in 0.03s ==============================
```

Full package test suite: **11 passed** (4 scaffold from 11-01 + 7 nupkg from 11-04).

### Sanity .nupkg inspection

```
bytes: 2440
  [Content_Types].xml
  _rels/.rels
  content/Main.py
  content/entry-points.json
  content/operate.json
  package/services/metadata/core-properties/2e344ab419ba4686.psmdcp
  sanity.nuspec
```

- Trivial `print(1)` script → **2,440 bytes** (sub-2.5KB as expected).
- **Confirmed `content/operate.json` present; `content/project.json` absent.**
- Psmdcp basename `2e344ab419ba4686` is exactly 16 hex chars.

## D-16 Correction — Explicit Call-Out

CONTEXT.md **D-16** originally specified:

> Cross-Platform layout: `content/Main.py`, `content/project.json`, `[Content_Types].xml`, `_rels/.rels`, `<package>.nuspec`.

RESEARCH.md **Finding 4** verified this is wrong by downloading `cli_pack.py` directly from `github.com/UiPath/uipath-python`. The authoritative CLI writes `content/operate.json` (+ `content/entry-points.json`), NOT `content/project.json`. `project.json` is the Studio IDE project file from 2021 — it is not what modern Orchestrator expects for runtime.

**Our implementation follows Finding 4, not D-16's literal wording.** The correction is guarded at three layers:

1. **Docstring** in `nupkg.py:9-13` explicitly calls out the D-16 correction.
2. **Grep-clean code**: `grep -c '"content/project.json"' nupkg.py` returns `0`.
3. **Explicit regression assertion** in `test_nupkg_has_required_files`: `assert "content/project.json" not in names  # Pitfall 6 guard`.

Future planners MUST NOT "fix" the implementation to match D-16 without first re-reading RESEARCH.md Finding 4.

## Deviations from Plan

**None.** Plan 11-04 executed exactly as written. No auto-fixes (Rule 1/2/3) triggered; no architectural checkpoint (Rule 4) needed. No authentication gates. No CLAUDE.md conflicts (nupkg.py is package-local code — no core `yigthinker/` edits, D-01 architect-not-executor invariant preserved).

## Known Stubs

**None** — `build_nupkg` is fully wired and returns real .nupkg bytes. No hardcoded empty values, no "coming soon" placeholders, no components awaiting data sources. Plan 11-05 can consume this directly.

## Deferred Items

**Per Finding 4 caveat:** `content/package-descriptor.json` and `content/bindings_v2.json` are intentionally omitted from the MVP. Orchestrator MAY reject a package without `package-descriptor.json`. If UAT against a real tenant shows an "invalid package" error, add per the Finding 4 verbatim schema (logged in PITFALLS.md). This is explicitly scoped to 11-HUMAN-UAT.md, not to any unit test.

## Commits

| # | Hash      | Subject                                                            |
|---|-----------|--------------------------------------------------------------------|
| 1 | `8a48a8f` | test(11-04): add failing test_nupkg.py for build_nupkg (RED)       |
| 2 | `c4c24b1` | feat(11-04): implement build_nupkg pure function (GREEN)           |

## Success Criteria (from 11-04-PLAN.md)

- [x] 7 tests in `tests/test_nupkg.py` pass.
- [x] `build_nupkg` importable as `from yigthinker_mcp_uipath.nupkg import build_nupkg`.
- [x] D-16 correction (operate.json instead of project.json) enforced by implementation AND by the `assert "content/project.json" not in names` regression guard.
- [x] Pitfall 5 (NuGet UTF-8 BOM) addressed by the `\ufeff` prefix in `_NUSPEC_TPL`.
- [x] Pure-function invariant verified by `test_pure_function_no_disk_write`.
- [x] Plan 11-05 `ui_deploy_process` handler can call `build_nupkg(...)` directly.

## Self-Check: PASSED

- `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/nupkg.py` — FOUND (152 lines, `def build_nupkg` present)
- `packages/yigthinker-mcp-uipath/tests/test_nupkg.py` — FOUND (112 lines, 7 tests)
- Commit `8a48a8f` — FOUND in git log
- Commit `c4c24b1` — FOUND in git log
- Pitfall 6 regression guard `assert "content/project.json" not in names` — FOUND at `tests/test_nupkg.py:37`
- Full `python -m pytest tests/test_nupkg.py` — 7/7 PASSED (verified in this session)
- Full `python -m pytest` (package) — 11/11 PASSED (4 scaffold + 7 nupkg)
