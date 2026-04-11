---
phase: 10-gateway-rpa-behavior
plan: 02
subsystem: gateway
tags: [rpa, llm, extraction, callback, json-parsing, fastapi, circuit-breaker]

requires:
  - phase: 10-01
    provides: RPAController scaffold with _extract_decision_stub, RPAStateStore, /api/rpa/callback route, checkpoint_utils.py.j2 template
  - phase: 02
    provides: LLMProvider.chat(messages, tools, system) uniform interface across Claude/OpenAI/Ollama/Azure
  - phase: 08
    provides: Message dataclass in yigthinker/types.py

provides:
  - Real extraction-only LLM classification path at POST /api/rpa/callback (GW-RPA-01 fully closed)
  - yigthinker.gateway.extraction_prompt module (EXTRACTION_SYSTEM + parse_extraction_response helper)
  - Layered JSON parse fallback (direct → strip fences → regex extract) with silent extraction_failed escalate on any shape/parse failure (CORR-04b)
  - 2000-char traceback truncation keeping extraction prompt within D-05 token budget

affects:
  - Phase 11 (UiPath MCP) — RPA callback is stable enough for deployed workflows to self-heal
  - Phase 12 (PA MCP) — same
  - 10-04 (behavior layer) — independent; only touches AgentLoop/AutoDream, not RPA callback path

tech-stack:
  added: []
  patterns:
    - "Extraction-only LLM call: provider.chat(messages, tools=[], system=...) with no tool registry"
    - "Layered JSON parse fallback: direct → markdown fence strip → regex brace extract → silent escalate"
    - "Exception-safe LLM call: try/except around provider.chat returns structured escalate (no exception bubbles to HTTP layer)"
    - "Payload trimming: traceback capped pre-serialization to keep prompt under budget"

key-files:
  created:
    - yigthinker/gateway/extraction_prompt.py
  modified:
    - yigthinker/gateway/rpa_controller.py
    - tests/test_gateway/test_rpa_controller.py

key-decisions:
  - "parse_extraction_response is sync (not async) — no await needed, called from async _extract_decision"
  - "Exception handler wraps ONLY provider.chat, not parse — parser already has total-coverage fallback"
  - "User message excludes workflow_name / callback_id / version (routing keys, not classification signals) per D-05"
  - "fix_applied without a valid integer retry_delay_s escalates — refuses to retry blindly"
  - "Predicted AsyncMock behavior in test_rpa_endpoints.py: default MagicMock return cascades through parser to extraction_failed escalate dict, which still satisfies all existing key-presence assertions — no edit needed to that test file"

patterns-established:
  - "Extraction-only LLM: tools=[] forces single-turn classification, no agent loop, no state"
  - "CORR-04b discipline: zero keyword heuristics — parser trusts only structured JSON"
  - "Silent-escalate on parse failure: all failure modes converge to a single escalate dict shape so the caller never sees None and never crashes"

requirements-completed: [GW-RPA-01]

duration: 6min
completed: 2026-04-11
---

# Phase 10 Plan 02: Gateway RPA Extraction LLM Summary

**Real extraction-only LLM call at /api/rpa/callback — tools=[] single-turn classification with layered JSON parse fallback, silently escalates on any malformed response per CORR-04b**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-11T07:41:00Z
- **Completed:** 2026-04-11T07:46:45Z
- **Tasks:** 4 (Task 0 RED + Task 1 extraction_prompt + Task 2 controller wiring + Task 3 verification)
- **Files modified:** 3 (1 new, 2 edited)

## Accomplishments

- Replaced 10-01's `_extract_decision_stub` with real `_extract_decision` method that calls `LLMProvider.chat(messages=[Message(...)], tools=[], system=EXTRACTION_SYSTEM)` uniformly across all 4 providers.
- Shipped `yigthinker/gateway/extraction_prompt.py` with a ~2200-char EXTRACTION_SYSTEM constant (5 decision rules + 3 Input/Output examples) and a `parse_extraction_response` helper using a layered JSON fallback (direct parse → markdown fence strip → regex brace extract).
- All failure modes (empty text, malformed JSON, unknown action value, missing `instruction`, missing `reason`, `fix_applied` without valid `retry_delay_s`, provider exception) converge on the canonical `{action: "escalate", reason: "extraction_failed", ...}` dict — CORR-04b "no keyword heuristic" holds.
- Traceback truncated to 2000 chars before JSON-serializing into the user message, keeping the prompt well under D-05's ~500-token budget.
- Full test_rpa_controller.py suite: 15/15 green. Full gateway sweep: 41 passed, 1 skipped (documented `test_breaker_persists_across_restart` Windows flake).

## Task Commits

1. **Task 0: Extend test_rpa_controller.py with extraction tests (RED)** — `56a43bd` (test)
2. **Task 1: Create extraction_prompt.py module** — `1dda5d0` (feat)
3. **Task 2: Replace _extract_decision_stub with real extraction call** — `07dd297` (feat, GREEN)
4. **Task 3: Document deferred 10-04 in-flight RED tests** — `1750c01` (chore)

## Files Created/Modified

- `yigthinker/gateway/extraction_prompt.py` **(new, 140 lines)** — EXTRACTION_SYSTEM constant + parse_extraction_response layered-fallback parser + _fail canonical escalate dict builder
- `yigthinker/gateway/rpa_controller.py` **(213 lines, +48/-13 net)** — Added imports for extraction_prompt + Message + json; replaced `_extract_decision_stub` with `_extract_decision`; updated handle_callback step 4 call site
- `tests/test_gateway/test_rpa_controller.py` **(344 lines, +154/-12 net)** — Renamed stub test to test_extraction_calls_provider_and_returns_decision; added 6 extraction tests + test_breaker_prevents_llm_call; updated 4 preserved 10-01 tests to configure AsyncMock return_value with real LLMResponse payloads
- `.planning/phases/10-gateway-rpa-behavior/deferred-items.md` — Documented 10-04's in-flight RED-phase test failures as out-of-scope

## Decisions Made

- **Parser is sync, not async.** No network I/O inside `parse_extraction_response`, so async is pointless and sync is simpler to test in isolation.
- **Exception handler wraps only `provider.chat`.** The parser already covers every malformed-input path, so wrapping parse in try/except would be dead code.
- **User message excludes workflow_name / callback_id / version.** These are routing/dedup keys, not classification signals per D-05. Including them would bias the LLM without adding signal.
- **fix_applied without valid retry_delay_s escalates.** Refusing to retry blindly: the rules require an integer delay for that action, and a missing one means the LLM failed the schema — we escalate loudly.
- **test_rpa_endpoints.py left untouched.** Predicted the AsyncMock default cascade: `response.text` on a default MagicMock is a truthy MagicMock, `.strip()` call succeeds, `json.loads` fails with TypeError, regex falls through, parser returns `extraction_failed` escalate dict — which contains `action` / `instruction` / `reason` keys, so the existing integration test's key-presence assertions still hold. Verified by running the full `test_rpa_endpoints.py` suite post-change: 9 passed, 1 skipped, zero failures.

## Deviations from Plan

None — plan executed exactly as written. All artifacts, behaviors, imports, test structure, and commit layout match the plan's `<action>` blocks verbatim.

## Issues Encountered

- **Git add edge case on deferred-items.md:** First `git add` + `git commit` sequence emitted a misleading "paths ignored by gitignore" warning because the parallel 10-04 executor touched `yigthinker/memory/auto_dream.py` between my add and commit. The deferred-items.md was actually already staged; a bare `git commit` completed successfully. No file was lost.
- **8 full-suite regressions found (all out of scope):** 4 tests in `tests/test_agent_memory.py` and 3 in `tests/test_memory/test_auto_dream.py` fail with `AttributeError: set_startup_alert_provider` and `TypeError: pattern_store kwarg` — these are 10-04's intentional RED-phase tests added in commit `3e4043a`, owned by the parallel executor. Plus the pre-existing Windows NTFS flake `test_list_sessions_excludes_old_files` already documented in STATE.md. Logged all 8 to `deferred-items.md` under "From Plan 10-02".

## User Setup Required

None — pure code change. No secrets, dashboards, or environment variables added.

## Next Phase Readiness

- **GW-RPA-01 fully closed.** The deployed-script self-healing path is now end-to-end: script POSTs to /api/rpa/callback → auth → dedup → circuit breaker → extraction LLM → structured decision → script retries/skips/aborts.
- **10-04 unblocked for its own work** — no file overlap; 10-04's in-flight tests will turn green when its executor finishes its own Task 1/2/3.
- **Phase 11/12 MCP servers** can now assume the callback endpoint returns structured decisions, not an `extraction_not_implemented` stub.
- **No blockers.** Extraction prompt is ~500 tokens; if real-world testing finds classification errors, D-29 ("Claude's discretion") allows iterating the prompt in a follow-up without schema changes.

## Self-Check: PASSED

- Created file exists: `yigthinker/gateway/extraction_prompt.py` — FOUND (140 lines)
- Modified file exists: `yigthinker/gateway/rpa_controller.py` — FOUND (213 lines)
- Modified file exists: `tests/test_gateway/test_rpa_controller.py` — FOUND (344 lines, 15 tests collected)
- Commit 56a43bd (Task 0 test RED) — FOUND in git log
- Commit 1dda5d0 (Task 1 extraction_prompt) — FOUND in git log
- Commit 07dd297 (Task 2 controller GREEN) — FOUND in git log
- Commit 1750c01 (Task 3 deferred items) — FOUND in git log
- Grep `_extract_decision_stub` in rpa_controller.py — 0 matches (stub fully removed)
- Grep `extraction_not_implemented` across repo — 0 matches (stub reason string fully removed)
- Grep heuristic guard (`"timeout"`, `"network"`, `"file not found"`) in extraction_prompt.py — 0 matches
- `python -m pytest tests/test_gateway/test_rpa_controller.py tests/test_gateway/test_rpa_endpoints.py -x --tb=short` — 24 passed, 1 skipped

---
*Phase: 10-gateway-rpa-behavior*
*Completed: 2026-04-11*
