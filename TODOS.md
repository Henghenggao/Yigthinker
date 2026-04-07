# TODOS

Items identified during eng review (2026-04-07) and deferred from immediate implementation.

## From Eng Review

### ~~asyncio task reference leak in memory extraction~~ ✅ Fixed (quick-260407-o9s)
**Fixed in:** `928cf98` — `_background_tasks` set on AgentLoop with `add_done_callback` auto-cleanup.

### ~~Gateway token unprotected on Windows~~ ✅ Fixed (quick-260407-o9s)
**Fixed in:** `928cf98` — Platform-aware protection: `icacls /inheritance:r /grant:r %USERNAME%:F` on Windows, `chmod 600` on Unix.

### ~~SmartCompact.run() is synchronous~~ ✅ Fixed (quick-260407-o9s)
**Fixed in:** `928cf98` — `async def run()` with `await` at call site in `agent.py`.

## From Design Review (2026-04-07)

### ~~Create DESIGN.md with design tokens and component patterns~~ ✅ Fixed (quick-260407-o9s)
**Fixed in:** `71fd6e6` — `docs/DESIGN.md` with CSS custom properties, component states, layout, responsive breakpoints, and accessibility requirements.

### Web dashboard keyboard shortcut mapping
**What:** Define web-safe keyboard shortcuts for the dashboard that don't conflict with browser defaults.
**Why:** TUI has Ctrl+G (sessions), Ctrl+L (models), Ctrl+D (preview), Ctrl+T (thinking), Ctrl+O (tool cards). Web equivalents need Ctrl+Shift combos to avoid conflicts (Ctrl+L = browser address bar).
**Context:** Power users (repeat finance managers) will want keyboard shortcuts for session switching, model changing, vars panel toggle.
**Fix:** Map TUI shortcuts to web-safe equivalents (e.g., Ctrl+Shift+S for sessions, Ctrl+Shift+M for models). Document in DESIGN.md.
**Depends on:** Dashboard implementation.

### Mobile viewport design
**What:** Design a minimal mobile layout for viewports under 768px.
**Why:** Current spec shows "Open on desktop" which is a dead end. Even a degraded mobile view is better than blocking users.
**Context:** Finance managers primarily work at desks, but may check on phones occasionally. Deferred from initial scope to keep dashboard launch manageable. Depends on tablet layout being stable first.
**Fix:** Design stacked conversation layout, hidden sidebar with sheet-style vars panel, simplified tool cards.
**Depends on:** Dashboard implementation + tablet layout proving stable.

## From Eng Review #2 (2026-04-07) — Architecture Validation

### ~~CRITICAL: Gateway WebSocket has no origin validation~~ ✅ Already implemented
**Fixed in:** Origin validation with `_DEFAULT_ALLOWED_ORIGINS` + configurable `gateway.allowed_origins` already present in `gateway/server.py:59-89`. Tests in `tests/test_gateway/test_origin_validation.py`.

### CRITICAL: No static file serving capability in Gateway
**What:** Gateway (`gateway/server.py`) is a pure API server. It has no `StaticFiles` mount, no `FileResponse`. The design spec says "Gateway serves static HTML/JS at `/dashboard/`."
**Why:** Without this, there is no way to load the dashboard in a browser. This is the core of the architecture change.
**Fix:** Add `StaticFiles` mount at `/dashboard/assets` and SPA fallback route at `/dashboard/{path:path}` returning `index.html`. Add `aiofiles>=23.0` to `gateway` extra in `pyproject.toml`.
**Depends on:** Dashboard static files being created (index.html, app.js, styles.css).

### HIGH: `yigthinker dashboard` CLI command imports Dash directly
**What:** `__main__.py:86-101` imports `create_dash_app` from `dashboard.layout` and `create_app` from `dashboard.server`, starts uvicorn on port 8765. This breaks after Dash removal.
**Why:** Users who learned `yigthinker dashboard` will get an ImportError.
**Fix:** Rewrite as a convenience alias that starts the gateway and opens browser to `http://localhost:8766/dashboard/`. Or remove the command and document `yigthinker gateway` as the single entry point.
**Depends on:** Gateway static file serving being implemented.

### HIGH: dashboard/server.py and dashboard/layout.py become dead code
**What:** `dashboard/server.py` (152 lines) and `dashboard/layout.py` (37 lines) are fully replaced by static HTML/JS served from Gateway. `DashboardSessionBridge` (drilldown routing between separate processes) solves a problem that doesn't exist when dashboard and gateway share the same process.
**Why:** Dead code creates confusion about which path is active. But don't delete until the new dashboard is built — they're the reference for origin validation and the entry push pattern.
**Fix:** Delete both files after the new static dashboard is functional and tested.
**Depends on:** New dashboard implementation complete.

### HIGH: pyproject.toml dashboard extra has wrong dependencies
**What:** `pyproject.toml:47-52` `dashboard` extra includes `dash>=2.17.0`. After architecture change, Dash is not needed. `test` extra also includes `dash>=2.17.0`.
**Why:** Installing `pip install -e .[dashboard]` will pull in a framework we no longer use.
**Fix:** Remove the `dashboard` extra entirely. Merge `plotly>=5.22.0` into core deps (chart tools use it regardless). Add `aiofiles>=23.0` to `gateway` extra. Remove `dash` from `test` extra.
**Depends on:** Dashboard migration complete.

### MEDIUM: Dashboard test suite tests old architecture
**What:** `tests/test_dashboard/` (4 files) tests `DashboardSessionBridge`, `create_dash_app()`, drilldown routing, and entry push. All test the Dash-based architecture being removed.
**Why:** Tests will break after migration. Need replacement tests for the new architecture.
**Fix:** After migration, replace with: (1) Gateway serves `index.html` at `/dashboard/`, (2) Gateway origin validation on WebSocket, (3) Gateway serves static assets. Port origin validation test logic from `test_server.py`.
**Depends on:** Dashboard migration complete.

### MEDIUM: DashboardEntry model has no path forward
**What:** `dashboard/server.py:22-26` defines `DashboardEntry` with push API. Old pattern: tool creates chart → POST to `/api/dashboard/push` → dashboard receives. New pattern: charts flow through conversation as `tool_result` → Gateway broadcasts via WebSocket → dashboard renders inline.
**Why:** `DashboardEntry` and the push API are dead patterns.
**Fix:** Remove with old dashboard code. No replacement needed — charts are conversation content.
**Depends on:** Dashboard migration complete.
