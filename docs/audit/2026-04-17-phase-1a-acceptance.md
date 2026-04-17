# Phase 1a Acceptance Gate — 2026-04-17

Spec: `docs/superpowers/specs/2026-04-17-yigthinker-phase-1-design.md` §2.3
Plan: `docs/superpowers/plans/2026-04-17-phase-1a-harvest-and-docs.md`
Branch: `claude/phase-1a-harvest-and-docs`

## Gate items

- [x] 8 ADRs at `docs/adr/001-*.md` through `008-*.md` (all present)
- [x] All 8 ADRs pass `scripts/check_adr_format.py` (exit 0 on `docs/adr`)
- [x] `MemoryProvider` Protocol + `MemoryRecord` in `yigthinker/memory/provider.py`
- [x] `FileMemoryProvider` impl + contract tests (`tests/test_memory/test_provider_contract.py`, 8 tests) + file-specific tests (`tests/test_memory/test_file_provider.py`, 5 tests) — all green
- [x] `yigthinker/memory/ltm_schema.py` + `yigthinker/memory/agent_profile.py` importable (dormant SQLAlchemy schemas, shared `Base`)
- [x] `yigthinker/presets/personas/*.json` — **25 files** (spec floor ≥ 16)
- [x] `yigthinker/presets/teams/*.json` — **3 files** (spec floor ≥ 2)
- [x] H1: installer re-export landed (`DEFAULT_INSTALL_SOURCE`, `INSTALL_SOURCE_ENV` re-exported; 15/15 installer tests pass)
- [x] H2: `test_infinite_loop_is_killed` marked `@pytest.mark.slow`; `slow` marker registered; `addopts = "-m 'not slow'"` default
- [x] H3: `tests/test_channels/test_feishu_send_response.py` green (3 tests)
- [x] H4: `tests/test_agent_definitional_reply.py` green (1 test)
- [x] Parent spec §6.4 + §6.2 correction committed to `claude/condescending-cartwright` (commit `88247cc`)
- [x] Pure-core CI matrix: `pip install yigthinker` (no extras) → **81/81** Phase 1a memory/preset/scripts/builder tests green; 16/16 H1/H2 tests green (1 correctly deselected by slow marker). Channel tests (Feishu) legitimately require `gateway`/`test` extras due to top-level `fastapi` import — not a Phase 1a regression.
- [x] `CLAUDE.md` `## Key Abstractions` section describes `MemoryProvider` (commit `1c9dd29`)

## Test numbers

- **Full pytest (default, `-m 'not slow'`)**: 1042 passed, 1 skipped, 1 deselected (the slow-gated `test_infinite_loop_is_killed`), **0 failed**. The two pre-existing Phase 0 carryover failures (`test_registry_has_20_tools`, `test_df_load_description_mentions_artifact_write`) were also fixed in this branch — see commit `b6c47b7` (test-only stale-expectation updates; no source changes).
- **Slow-only (`-m slow`)**: 1 passed (the `test_infinite_loop_is_killed` timeout gate fires correctly)
- **ADR validator**: exit 0 on all 8 ADRs in `docs/adr/`
- **Pure-core subset** (81 tests): all green under `pip install yigthinker` with zero extras

## Commit chain (this branch)

```
b6c47b7 test(tools): fix stale baseline expectations (registry count + df_load wording)
082c26a test(agent): regression for definitional direct-reply path (H4)
2d46c11 test(feishu): integration coverage for send_response (H3)
1c9dd29 docs(CLAUDE.md): document MemoryProvider abstraction
966b2a3 test(df_transform): mark infinite-loop timeout test as slow (opt-in via -m slow)
ac08bcf fix(cli): re-export DEFAULT_INSTALL_SOURCE from installer for existing tests
ea85e6b feat(presets): harvest Yigcore persona cards (25) + team cards (3)
aa63537 feat(memory): port Yigcore core-memories schema as AgentProfile (dormant)
7fc49cf feat(memory): port Yigcore LTM V1 schema to SQLAlchemy (dormant)
8dd80eb feat(builder): add build_memory_provider helper (default 'null')
309099f feat(session): add opt-in ctx.memory: MemoryProvider field (default None)
73f64ce feat(memory): add FileMemoryProvider (stdlib+filelock JSONL store)
3404221 feat(memory): add MemoryProvider Protocol + MemoryRecord model
6c92da9 docs(adr): 008 — persona as data (rewrite from PersonaCard convergence spec)
613a7d9 docs(adr): 007 — plugin and skill distribution (rewrite from Yigcore ADR-014 + ADR-015)
d098fbb docs(adr): 006 — workflow templating (rewrite from Yigcore ADR-037)
eb27df9 docs(adr): 005 — MemoryProvider interface (rewrite from Yigcore LTM V1 spec)
ca2e725 docs(adr): 004 — governance as pluggable sidecar (rewrite from Yigcore ADR-001 + Sentinel 4-layer)
171e1aa docs(adr): 003 — harness philosophy (rewrite from Yigcore ADR-036)
b62ff7c docs(adr): 002 — intent-first routing (rewrite from Yigcore ADR-016)
b76a36a docs(adr): 001 — why we don't do PGEC (rewrite from Yigcore ADR-038 + ADR-008)
7dc23f9 docs(adr): add README index + template
7e1a513 feat(scripts): add ADR format validator (check_adr_format.py)
```

Parent-spec commit (on `claude/condescending-cartwright`): `88247cc`.

## Open observations (non-blocking, noted for follow-up phases)

1. **`FeishuAdapter.send_response(vars_summary=...)` kwarg is silently dropped.** Task 20's integration test confirmed the adapter accepts but doesn't propagate `vars_summary` into the card body. Not a Phase 1a regression — the test pins current behavior, not ideal behavior. Worth filing as a Phase 2 bug if IM channel parity matters.
2. ~~**Pre-existing failures (x2)**: `test_registry_has_20_tools` and `test_df_load_description_mentions_artifact_write`.~~ **Resolved in commit `b6c47b7`** — both were stale test expectations (registry now has 27 tools after `artifact_write` was added; df_load description was reworded to "load tabular data"). Fix is test-only; tool source untouched.

## Ready to merge

**Yes.** Every §2.3 gate item is satisfied. Phase 1a produces no regressions on the existing green baseline, and the 2 pre-existing Phase 0 failures were also fixed as a courtesy cleanup — the default suite is now fully green (1042 passed, 0 failed).

Phase 1b (agent.py core-loop work — MemoryProvider integration into the agent loop, action-first prompt tightening) can now start from this branch's tip.
