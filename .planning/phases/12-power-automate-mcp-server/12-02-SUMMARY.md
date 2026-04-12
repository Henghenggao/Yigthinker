---
phase: 12-power-automate-mcp-server
plan: 02
subsystem: auth
tags: [msal, oauth2, asyncio-lock, power-automate, azure-ad, cached-property]

# Dependency graph
requires:
  - phase: 12-01
    provides: PowerAutomateAuth stub with dataclass fields and NotImplementedError
provides:
  - MSAL ConfidentialClientApplication wrapper with token caching and refresh
  - PowerAutomateAuth.get_token() async method for all 5 tool handlers
  - DEFAULT_SCOPE, DEFAULT_AUTHORITY, SAFETY_MARGIN_S constants
affects: [12-03, 12-05, 12-06]

# Tech tracking
tech-stack:
  added: [msal ConfidentialClientApplication]
  patterns: [cached_property for lazy MSAL app, instance __dict__ mock injection for cached_property tests]

key-files:
  created:
    - packages/yigthinker-mcp-powerautomate/tests/test_auth.py
  modified:
    - packages/yigthinker-mcp-powerautomate/yigthinker_mcp_powerautomate/auth.py

key-decisions:
  - "MSAL app created via @cached_property on _app -- lazy initialization avoids network at import time"
  - "Tests inject mocks via instance __dict__ (not class-level property replacement) to prevent test cross-contamination with cached_property"
  - "get_token() takes no parameters -- MSAL manages its own HTTP internally (key difference from Phase 11 UiPath auth which takes httpx.AsyncClient)"

patterns-established:
  - "MSAL mock pattern: auth.__dict__['_app'] = mock_app for cached_property injection"
  - "monkeypatch on yigthinker_mcp_powerautomate.auth.msal.ConfidentialClientApplication for authority tests"

requirements-completed: [MCP-PA-02]

# Metrics
duration: 4min
completed: 2026-04-12
---

# Phase 12 Plan 02: PowerAutomateAuth MSAL Token Acquisition Summary

**MSAL ConfidentialClientApplication wrapper with token caching, 60s safety-margin refresh, and asyncio.Lock thundering-herd guard -- key structural departure from Phase 11 (MSAL vs raw httpx OAuth2)**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-12T09:28:25Z
- **Completed:** 2026-04-12T09:33:05Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 2

## Accomplishments
- 7 unit tests covering full D-27 Row 1 test matrix: token acquisition, caching, expiry refresh, MSAL error handling, concurrent lock guard, custom scope, default authority
- MSAL ConfidentialClientApplication wrapper with cached_property lazy initialization
- asyncio.Lock via field(default_factory=asyncio.Lock) preventing thundering-herd (D-09)
- scopes passed as list[str] to acquire_token_for_client (MSAL 1.23+ requirement)
- get_token() takes no parameters -- MSAL manages its own HTTP (D-08)
- RuntimeError raised on MSAL error responses with error code in message
- All constraints verified: min 50 lines (84 actual), correct exports, no forbidden patterns

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write 7 failing tests** - `6c6f924` (test)
2. **Task 2: GREEN -- Implement auth.py** - `8709395` (feat)

## Files Created/Modified
- `packages/yigthinker-mcp-powerautomate/tests/test_auth.py` - 7 unit tests mocking MSAL via monkeypatch (NOT respx per D-26)
- `packages/yigthinker-mcp-powerautomate/yigthinker_mcp_powerautomate/auth.py` - MSAL ConfidentialClientApplication wrapper (84 lines, replaces NotImplementedError stub)

## Decisions Made
- Used `@cached_property` for `_app` to lazily create the MSAL app, avoiding network calls at import time and enabling clean test injection via `auth.__dict__["_app"]`
- Tests use instance `__dict__` injection for the `cached_property` mock rather than class-level `property()` replacement, preventing cross-test contamination
- Authority default uses string formatting: `https://login.microsoftonline.com/{tenant_id}` -- matches MSAL common pattern

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None -- auth.py is fully implemented with no remaining stubs.

## Next Phase Readiness
- PowerAutomateAuth is ready for Plan 12-03 (client.py) which will use `auth.auth_headers()` for API calls
- Plan 12-05 tool handlers will use `auth.get_token()` / `auth.auth_headers()` for Bearer token injection

## Self-Check: PASSED

- [x] auth.py exists at expected path
- [x] test_auth.py exists at expected path
- [x] 12-02-SUMMARY.md created
- [x] RED commit 6c6f924 found in git log
- [x] GREEN commit 8709395 found in git log
- [x] All 7 tests pass
- [x] All plan constraints verified (asyncio.Lock pattern, scopes list, time.monotonic, no-param get_token, cached_property, MSAL CCA, min 50 lines)

---
*Phase: 12-power-automate-mcp-server*
*Completed: 2026-04-12*
