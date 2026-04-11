---
phase: 11-uipath-mcp-server
plan: 02
subsystem: uipath-mcp-package
tags: [oauth2, auth, httpx, asyncio-lock, tdd, wave-1]
wave: 1
requirements: [MCP-UI-02]
one_liner: "UipathAuth OAuth2 client credentials flow with token caching, refresh, 401 propagation, and asyncio.Lock concurrency guard"
dependency_graph:
  requires:
    - "11-01 (yigthinker_mcp_uipath package scaffold + conftest fixtures)"
  provides:
    - "UipathAuth dataclass importable from yigthinker_mcp_uipath.auth"
    - "TOKEN_URL constant ('https://cloud.uipath.com/identity_/connect/token') for Plan 11-03 OrchestratorClient tests"
    - "SAFETY_MARGIN_S = 60 constant for downstream refresh behavior"
    - "async get_token(http) and auth_headers(http) methods for Plan 11-05 tool handlers"
  affects:
    - "Plan 11-03 OrchestratorClient (depends on UipathAuth for Bearer token injection)"
    - "Plan 11-05 tool handlers (ui_deploy_process, ui_trigger_job, ui_job_history, ui_manage_trigger, ui_queue_status — all inject auth_headers)"
tech_stack:
  added:
    - "None — uses only httpx + stdlib (asyncio, time, dataclasses) already declared in Plan 11-01"
  patterns:
    - "@dataclass with asyncio.Lock via field(default_factory=asyncio.Lock) (NOT default=asyncio.Lock() — shared lock bug)"
    - "time.monotonic() for expiry clock (monkeypatchable via module-level time import)"
    - "resp.raise_for_status() to propagate 401/4xx as httpx.HTTPStatusError"
    - "OAuth2 RFC 6749 space-separated scope string (Pitfall 3 guard — never comma-separated)"
    - "asyncio.Lock thundering-herd guard (Pitfall 4)"
key_files:
  created:
    - "packages/yigthinker-mcp-uipath/tests/test_auth.py (133 lines, 6 tests)"
  modified:
    - "packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/auth.py (stub → 73-line implementation)"
decisions:
  - "Locked D-09 constructor signature kept verbatim: 5 positional fields, scope is a single space-separated str"
  - "D-10 env-var name confirmed: UIPATH_SCOPE (singular) — matches README and conftest fixture"
  - "asyncio.Lock held across the entire get_token() call (including the cache-hit branch) so concurrent callers all see the same post-acquire state — simplest correct implementation"
  - "30s httpx timeout matches D-13 (OrchestratorClient will reuse the same budget)"
  - "No retry logic inside UipathAuth — retries belong to OrchestratorClient per D-13. 401 propagates immediately as httpx.HTTPStatusError"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-11"
  tasks: 2
  tests_added: 6
  tests_passing: 6
  files_created: 1
  files_modified: 1
---

# Phase 11 Plan 02: UipathAuth OAuth2 Implementation Summary

Ship the OAuth2 client credentials authentication module for the `yigthinker-mcp-uipath` MCP server. This is the only auth path Phase 11 supports (D-08 — cloud tenants only, no on-prem API key) and the interface is consumed by Plan 11-03 (`OrchestratorClient`) and Plan 11-05 (5 tool handlers).

## What Was Built

### `UipathAuth` dataclass (`packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/auth.py`)

Final shipped signature — **exactly as locked in CONTEXT.md D-09**, no deviations:

```python
@dataclass
class UipathAuth:
    client_id: str
    client_secret: str
    tenant_name: str
    organization: str
    scope: str                        # space-separated per RFC 6749
    _token: str | None = field(default=None, repr=False)
    _expires_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get_token(self, http: httpx.AsyncClient) -> str: ...
    async def auth_headers(self, http: httpx.AsyncClient) -> dict[str, str]: ...
```

**Module-level constants** (exported for Plan 11-03 tests):

| Constant | Value |
|---|---|
| `TOKEN_URL` | `"https://cloud.uipath.com/identity_/connect/token"` |
| `SAFETY_MARGIN_S` | `60` |

Both are importable via `from yigthinker_mcp_uipath.auth import TOKEN_URL, SAFETY_MARGIN_S, UipathAuth`.

### Test suite (`packages/yigthinker-mcp-uipath/tests/test_auth.py`)

6 respx-mocked unit tests covering the full D-23 auth matrix:

| # | Test | What it proves |
|---|---|---|
| 1 | `test_token_acquisition_and_caching` | First call POSTs once; second call within expiry returns cached token without HTTP request (`call_count == 1`) |
| 2 | `test_form_body_uses_space_separated_scope` | Form body contains `grant_type=client_credentials`, `scope=OR.Execution+OR.Jobs+OR.Folders.Read`, and **never** `%2C` or `,` (Pitfall 3 guard) |
| 3 | `test_token_refresh_on_expiry` | Monkeypatch `time.monotonic`; advancing past `expires_in - SAFETY_MARGIN_S` triggers exactly one refresh POST (`call_count == 2`) |
| 4 | `test_401_on_invalid_credentials` | 401 response → `httpx.HTTPStatusError` surfaces via `raise_for_status()` |
| 5 | `test_auth_headers_returns_bearer` | `auth_headers()` returns `{"Authorization": "Bearer tok-1"}` |
| 6 | `test_concurrent_get_token_one_request` | `asyncio.gather(get_token × 3)` triggers exactly 1 POST (Pitfall 4 asyncio.Lock guard) |

## Test Results

```
cd packages/yigthinker-mcp-uipath && python -m pytest tests/test_auth.py -v
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.2, pluggy-1.6.0
plugins: anyio-4.13.0, dash-4.1.0, asyncio-1.3.0, mock-3.15.1, respx-0.23.1
collected 6 items

tests/test_auth.py::test_token_acquisition_and_caching PASSED            [ 16%]
tests/test_auth.py::test_form_body_uses_space_separated_scope PASSED     [ 33%]
tests/test_auth.py::test_token_refresh_on_expiry PASSED                  [ 50%]
tests/test_auth.py::test_401_on_invalid_credentials PASSED               [ 66%]
tests/test_auth.py::test_auth_headers_returns_bearer PASSED              [ 83%]
tests/test_auth.py::test_concurrent_get_token_one_request PASSED         [100%]

============================== 6 passed in 1.07s ==============================
```

**6/6 passing, 1.07s runtime, zero warnings, zero deprecations.**

Full-package regression run (scaffold tests + auth tests): `10 passed in 1.10s`.

## Commits

| Hash | Subject |
|---|---|
| `1ad2c38` | test(11-02): add failing test_auth.py for UipathAuth OAuth2 flow |
| `0ec926f` | feat(11-02): implement UipathAuth OAuth2 client credentials flow |

## Deviations from Plan

**None.** The plan specified the exact test code and the exact implementation (copied verbatim from RESEARCH.md Pattern 2). Both were shipped as written. No deviation rules triggered:
- No bugs to auto-fix (Rule 1)
- No missing critical functionality (Rule 2)
- No blocking issues (Rule 3)
- No architectural changes needed (Rule 4)

## Truth Checks (from plan `must_haves.truths`)

- [x] `UipathAuth` class exists with the exact constructor signature locked in D-09
- [x] OAuth2 token acquisition POSTs to `https://cloud.uipath.com/identity_/connect/token` with form-encoded body and `grant_type=client_credentials`
- [x] Token caching: a second `get_token()` call within `expires_in - 60s` safety margin returns the cached token without a second HTTP request (test 1, `call_count == 1`)
- [x] Token refresh: a `get_token()` call after expiry triggers exactly one new POST to the token endpoint (test 3, `call_count == 2`)
- [x] 401 invalid_credentials raises `httpx.HTTPStatusError` (test 4)
- [x] `asyncio.Lock` prevents thundering-herd: 3 concurrent `get_token()` calls trigger exactly one POST (test 6, `call_count == 1`)

## Artifacts (from plan `must_haves.artifacts`)

- [x] `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/auth.py` — 73 lines (required ≥50), contains `class UipathAuth`
- [x] `packages/yigthinker-mcp-uipath/tests/test_auth.py` — 133 lines (required ≥80), contains `test_token_acquisition_and_caching`

## Key Links (from plan `must_haves.key_links`)

- [x] `UipathAuth.get_token` → `https://cloud.uipath.com/identity_/connect/token` via `httpx.AsyncClient.post` with `grant_type=client_credentials` form body
- [x] `tests/test_auth.py` → `respx.post(TOKEN_URL)` via `@respx.mock` + `route.call_count` assertions

## Known Stubs

**None.** `auth.py` is fully implemented; nothing returns `[]` / placeholder text / `NotImplementedError`.

## Deferred Issues

**None.**

## MCP-UI-02 Status

MCP-UI-02 is **implemented at the code level** by this plan. End-to-end verification (real UiPath tenant OAuth2 round-trip) still requires:
- Plan 11-03 `OrchestratorClient` (Wave 1, parallel)
- Plan 11-05 tool handlers (Wave 2)
- Plan 11-06 server wiring (Wave 3)
- 11-HUMAN-UAT.md live tenant test (manual)

## Self-Check: PASSED

- Created file `packages/yigthinker-mcp-uipath/tests/test_auth.py`: FOUND
- Modified file `packages/yigthinker-mcp-uipath/yigthinker_mcp_uipath/auth.py`: FOUND
- Commit `1ad2c38` (test(11-02)): FOUND
- Commit `0ec926f` (feat(11-02)): FOUND
- `TOKEN_URL` importable: YES (verified via `from yigthinker_mcp_uipath.auth import TOKEN_URL`)
- `SAFETY_MARGIN_S` importable: YES
- `UipathAuth` importable: YES
- All 6 required tests in test file: YES
- Pitfall 3 guard present (`scope=OR.Execution+OR.Jobs+OR.Folders.Read`): YES
- Pitfall 4 guard present (`asyncio.gather(`): YES
