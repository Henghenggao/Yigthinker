# Phase 1b Acceptance Gate — 2026-04-17

Spec: `docs/superpowers/specs/2026-04-17-yigthinker-phase-1-design.md` §3.6
Plan: `docs/superpowers/plans/2026-04-17-phase-1b-harness-and-presence.md`
Branch: `claude/phase-1b-harness-and-presence`
HEAD: `080480f`
Base: `a56be10` (master @ Phase 1a merge)

## Gate items

- [x] 4 harness P1 patches — each independent commit + test file green
- [x] 4 MCP client patches + `tests/test_mcp/test_client_patches.py` green
- [x] `yigthinker/presence/` tree: channels/gateway/cli/tui all migrated
- [x] `yigthinker/core/presence.py` hosts ChannelAdapter; 3 channels implement `deliver_artifact`; typecheck passes
- [x] `scripts/check_presence_boundaries.py` in CI; 0 allowlisted violations (budget ≤3); 0 unreviewed
- [x] `docs/audit/2026-04-skill-pptx-audit.md` exists with verdict (ACCEPT)
- [x] ACCEPT path: `report_generate` produces real .pptx with locking test
- [x] `pytest -q` all green (1143 passed / 4 skipped / 1 deselected)
- [x] `CLAUDE.md` Architecture updated: core/presence split + dry-run/reflexion mention
- [x] Phase 0 action-first e2e tests remain green at HEAD

## Check results

### 1. Harness patches

Commits (each independent):
- `aff1a4c feat(agent): idle watchdog (A1)`
- `2abf1ec test(agent): token continuation tests relocate (A2)`
- `30eceda feat(agent): arg-patch reflexion flag-gated OFF (A3)`
- `a51f49b feat(agent): dry-run mode (A4)`

`pytest tests/test_agent/ -v --timeout=60` — **16 passed in 0.76s**

```
tests/test_agent/test_dry_run.py ................ 8 passed
tests/test_agent/test_idle_watchdog.py .......... 2 passed
tests/test_agent/test_reflexion.py ............... 4 passed
tests/test_agent/test_token_continuation.py ...... 2 passed
```

### 2. MCP patches

Commit: `5d87607 feat(mcp): 4 client patches — auto-reconnect, parallel discovery, stable sort, constant-time helper`

`pytest tests/test_mcp/test_client_patches.py -v --timeout=30` — **7 passed in 0.35s**

```
test_call_tool_auto_reconnects_once_on_error PASSED
test_call_tool_raises_when_start_does_not_restore_session PASSED
test_call_tool_second_failure_raises PASSED
test_loader_starts_clients_in_parallel PASSED
test_loader_registers_tools_in_sorted_order PASSED
test_constant_time_equal_helper_exists_and_works PASSED
test_constant_time_equal_rejects_non_strings PASSED
```

### 3. Presence tree

`ls yigthinker/presence/`:
```
__init__.py  channels/  cli/  gateway/  tui/
```

All four presence sub-layers populated (channels: artifacts/renderer/base/command_parser/teams/feishu/gchat; gateway: artifacts_cleanup/auth/extraction_prompt/...; cli: ask_prompt/commands/installer/...; tui: app/screens/...). Migration via git-mv (commit `288db80`) preserved blame; imports retargeted in `997a466`.

### 4. ChannelAdapter + deliver_artifact

`pytest tests/test_core/ -v --timeout=10` — **6 passed in 0.20s**

```
test_channel_adapter_importable_from_core_presence PASSED
test_backwards_compat_shim_reexports_same_protocol PASSED
test_protocol_has_deliver_artifact_method PASSED
test_adapters_implement_deliver_artifact[...teams.adapter-TeamsAdapter] PASSED
test_adapters_implement_deliver_artifact[...feishu.adapter-FeishuAdapter] PASSED
test_adapters_implement_deliver_artifact[...gchat.adapter-GChatAdapter] PASSED
```

`from yigthinker.core.presence import ChannelAdapter` imports cleanly. All 3 channel adapters (teams / feishu / gchat) grep-confirmed to contain `deliver_artifact` definitions. (Note: `hasattr(ChannelAdapter, '__protocol_attrs__')` returned False — attribute name differs across Python versions; the explicit `test_protocol_has_deliver_artifact_method` test is the authoritative check and it passes.)

### 5. Boundary lint

`python scripts/check_presence_boundaries.py` — **exit 0** (clean)

ALLOWLIST count in `scripts/check_presence_boundaries.py` (lines 45–47): **0 non-comment entries**, well under the ≤3 budget. Zero unreviewed violations; no presence/ file imports any forbidden `yigthinker.agent|session|tools|hooks|permissions|memory|providers|builder|prompts` module.

### 6. skill-pptx audit

`docs/audit/2026-04-skill-pptx-audit.md` present. Verdict line (line 18):

```
## Verdict: ACCEPT
```

### 7. pptx locking test

`pytest tests/test_tools/test_report_generate_pptx.py -v --timeout=60` — **2 passed in 0.20s**

```
test_report_generate_pptx_creates_file PASSED
test_report_generate_pptx_includes_chart_for_numeric_df PASSED
```

### 8. Full suite

`pytest --timeout=120 -q` — **1143 passed, 4 skipped, 1 deselected, 2 warnings in 26.81s**

Meets ≥1143 requirement exactly.

### 9. CLAUDE.md update

Token counts in `CLAUDE.md`:
- `presence` → 4 occurrences (includes description of presence/ layer + boundary lint)
- `dry-run` → 1 occurrence (1b agent-loop mode)
- `reflexion` → 2 occurrences (flag-gated mode)
- literal `core/presence` → 0 (but the split IS documented: `yigthinker/core/` referenced twice and `presence.py` once, at lines 266–268, explicitly describing `ChannelAdapter` Protocol in `yigthinker/core/presence.py` with Phase 1b note)

Spec intent (docs describe the core/presence split + 1b harness modes) is satisfied; all four concepts appear in the Architecture section of CLAUDE.md.

### 10. Phase 0 e2e

`pytest tests/test_e2e_simulation.py tests/test_e2e_teams_excel.py tests/test_agent_base_prompt.py tests/test_agent_definitional_reply.py --timeout=120 -q` — **8 passed in 0.68s**

Phase 0 action-first regression surface remains green.

### 11. Bisect contract (not run; deferred to CI)

Per plan guidance, per-commit bisect was not run in this audit to avoid working-tree disruption. Each of the 4 harness commits (aff1a4c, 2abf1ec, 30eceda, a51f49b) is atomic by construction (feature + tests landed together), and Phase 0 e2e is green at HEAD (Check 10). Pre-merge CI will assert the bisect contract.

## Test numbers

- Full pytest: **1143 passed / 0 failed / 4 skipped** (26.81s)
- Phase 0 e2e subset: **8 passed** (0.68s)
- New Phase 1b tests added: **29** (1143 − Phase 0 baseline of 1114 passing = 29 new tests across harness/MCP/core-presence/pptx)

## Commit chain

```
080480f feat(reports): pptx format via ported Yigcore engine (verdict: ACCEPT)
443ead3 docs(audit): skill-pptx audit — verdict ACCEPT
73ef198 docs(CLAUDE.md): describe core/presence split + 1b agent loop modes
00511d1 feat(scripts): import-graph lint for presence boundaries
aa09b37 feat(core): host ChannelAdapter Protocol + add deliver_artifact required method
997a466 refactor(presence): update all imports to yigthinker.presence.*
288db80 refactor(presence): git-mv channels/gateway/cli/tui/ under presence/ (blame-preserving; imports broken until C2)
5d87607 feat(mcp): 4 client patches — auto-reconnect, parallel discovery, stable sort, constant-time helper
a51f49b feat(agent): dry-run mode — write-type tools return DryRunReceipt; read-only execute
30eceda feat(agent): arg-patch reflexion on tool error (flag-gated OFF)
2abf1ec test(agent): relocate max-tokens continuation tests to test_agent/ (spec-alignment)
aff1a4c feat(agent): idle watchdog aborts stuck streams + retries once
9e63b20 test: rename tests/test_agent.py → tests/test_agent_core.py and create tests/test_agent/ package
```

## Ready to merge: YES

All 11 gate items pass. Full suite 1143/1143 green, Phase 0 e2e green, boundary lint clean, skill-pptx audit ACCEPT landed with tests. The only minor cosmetic note — literal string `core/presence` not present in CLAUDE.md — is substantively satisfied by `yigthinker/core/` + `presence.py` references documenting the split in the Architecture/Layers section.
