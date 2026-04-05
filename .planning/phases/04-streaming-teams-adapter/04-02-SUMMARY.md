---
phase: 04-streaming-teams-adapter
plan: 02
subsystem: channels
tags: [teams, hmac, msal, adaptive-cards, bot-framework, httpx, webhook]

# Dependency graph
requires:
  - phase: 04-streaming-teams-adapter/01
    provides: "TeamsCardRenderer with render_thinking/render_text/render_error, SessionKey helpers, ChannelAdapter Protocol"
provides:
  - "HMAC-SHA256 signature verification for Teams outgoing webhooks"
  - "Async webhook handler with immediate 200 ACK and thinking card (D-05 pattern)"
  - "Bot Framework REST API send_response() with MSAL app token (TEAMS-02)"
  - "Session key derivation from AAD object ID (TEAMS-03)"
affects: [04-streaming-teams-adapter]

# Tech tracking
tech-stack:
  added: [hmac, msal, httpx]
  patterns: [immediate-ack-async-process, hmac-signature-verification, bot-framework-rest-api]

key-files:
  created:
    - yigthinker/channels/teams/hmac.py
    - tests/test_channels/__init__.py
    - tests/test_channels/test_teams_hmac.py
    - tests/test_channels/test_teams_adapter.py
  modified:
    - yigthinker/channels/teams/adapter.py

key-decisions:
  - "Use Bot Framework REST API (serviceUrl/v3/conversations) instead of Graph API for outgoing webhook responses"
  - "MSAL scope uses api.botframework.com/.default for Bot Framework API access"
  - "HMAC verification reads raw body bytes before JSON parsing to prevent signature mismatch"
  - "sys.modules mock pattern for msal in tests since msal not in dev dependencies"

patterns-established:
  - "Immediate ACK + async task pattern: return 200 with thinking card, asyncio.create_task for processing"
  - "HMAC verification as separate module for testability"
  - "sys.modules patching for optional dependency mocking in tests"

requirements-completed: [TEAMS-01, TEAMS-02, TEAMS-03]

# Metrics
duration: 3min
completed: 2026-04-05
---

# Phase 04 Plan 02: Teams Adapter HMAC, Async Webhook, and Graph API Response Summary

**Teams webhook with HMAC-SHA256 verification, immediate 200 ACK with thinking card, async agent processing, and Bot Framework REST API response delivery via MSAL tokens**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-05T19:16:02Z
- **Completed:** 2026-04-05T19:19:43Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- HMAC-SHA256 signature verification module with timing-safe comparison for Teams outgoing webhooks (TEAMS-01)
- Webhook returns 200 immediately with "Analyzing..." thinking card, agent processing runs async via create_task (D-05)
- send_response() delivers results via Bot Framework REST API with MSAL app-only token as Adaptive Cards (TEAMS-02)
- Session key derived from AAD object ID (per-sender) or channel ID (per-channel) with fallback (TEAMS-03)
- 12 tests covering HMAC verification, session key derivation, webhook ACK pattern, send_response, and HMAC rejection

## Task Commits

Each task was committed atomically:

1. **Task 1: Create HMAC-SHA256 verification, wire async webhook with immediate ACK, implement Graph API send_response** - `83ed2cd` (feat)
2. **Task 2: Teams adapter session key and webhook integration tests** - `db70733` (test)

## Files Created/Modified
- `yigthinker/channels/teams/hmac.py` - HMAC-SHA256 verification function and FastAPI dependency
- `yigthinker/channels/teams/adapter.py` - Full adapter with HMAC, immediate ACK, async processing, Bot Framework send_response
- `tests/test_channels/__init__.py` - Test package init
- `tests/test_channels/test_teams_hmac.py` - 5 HMAC verification unit tests
- `tests/test_channels/test_teams_adapter.py` - 7 adapter tests (session key, webhook ACK, send_response, HMAC rejection)

## Decisions Made
- Used Bot Framework REST API (serviceUrl/v3/conversations/{id}/activities) instead of Microsoft Graph API directly for outgoing webhook responses, since Teams outgoing webhooks provide a serviceUrl that points to the Bot Framework service
- MSAL scope set to "https://api.botframework.com/.default" for Bot Framework API token acquisition
- Raw body bytes used for HMAC verification before JSON parsing to prevent signature mismatch (Pitfall 3 from RESEARCH.md)
- Used sys.modules mock pattern for msal in tests since msal is an optional dependency not in the dev dependency group

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed msal mock strategy in adapter tests**
- **Found during:** Task 2 (adapter integration tests)
- **Issue:** Plan used `patch("yigthinker.channels.teams.adapter.msal", create=True)` but msal is imported locally inside `start()`, not at module level, so the patch had no effect. Additionally, msal is not installed in the test environment, causing `ImportError` and early return before route registration.
- **Fix:** Used `patch.dict(sys.modules, {"msal": mock_msal_module})` to inject a mock msal module into sys.modules, allowing the local `import msal` to succeed.
- **Files modified:** tests/test_channels/test_teams_adapter.py
- **Verification:** All 7 adapter tests pass
- **Committed in:** db70733 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix necessary for test correctness with optional dependency mocking. No scope creep.

## Issues Encountered
None beyond the msal mock strategy deviation above.

## User Setup Required
None - no external service configuration required. Teams adapter requires runtime MSAL credentials (tenant_id, client_id, client_secret, webhook_secret) configured in settings.json channels.teams section.

## Next Phase Readiness
- Teams adapter fully wired with HMAC verification, immediate ACK, and async response delivery
- Ready for end-to-end integration testing with actual Teams outgoing webhook configuration
- CardRenderer already provides render_thinking, render_text, render_error, render_dataframe_summary, render_chart_link

## Self-Check: PASSED

All created files verified present. All commit hashes verified in git log.

---
*Phase: 04-streaming-teams-adapter*
*Completed: 2026-04-05*
