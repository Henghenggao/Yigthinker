# Technology Stack

**Project:** Yigthinker — Multi-channel AI Agent Gateway, TUI, and Memory Systems
**Researched:** 2026-04-02

## Context

This stack research covers only the **new milestone scope**: Gateway daemon, TUI client, channel adapters (Feishu/Teams/Google Chat), session hibernation, and cross-session memory. The core Agent Loop, 21 tools, LLM providers, and CLI are already built and not re-evaluated here. The codebase already has stub implementations with dependency choices made — this research validates those choices and identifies version/configuration issues.

## Recommended Stack

### Gateway Server

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastAPI | >=0.135.0 | HTTP API + WebSocket endpoints for Gateway | Already in codebase. Built on Starlette ASGI, native WebSocket support, dependency injection, OpenAPI docs for free. The SSE support added recently is useful for future streaming alternatives. No reason to switch. | HIGH |
| uvicorn | >=0.42.0 | ASGI server | Standard production server for FastAPI. Supports `--workers` for multi-process (though single-worker is fine for this use case since sessions are in-process memory). Install with `uvicorn[standard]` for uvloop on Linux (unavailable on Windows). | HIGH |
| websockets | >=16.0 | TUI WebSocket client (not server) | Used by the TUI client to connect to Gateway. The server side uses FastAPI/Starlette's built-in WebSocket. v16.0 is current (Jan 2026), supports Python 3.10+, free-threaded Python. The codebase correctly uses this only client-side. | HIGH |

**Architecture note:** FastAPI's WebSocket IS Starlette's WebSocket — zero performance difference. The Gateway correctly uses FastAPI's `@app.websocket("/ws")` for the server side and `websockets` library for the TUI client side. This is the standard split.

### TUI Client

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| textual | >=8.0.0 | Terminal UI framework | Already chosen. Textual 8.x (Mar 2026) is the current major version. Rich widget library, CSS-like styling, async-native with worker API, screens/modals for session picker and model picker. The only serious Python TUI framework in 2025-2026. Alternatives (curses, urwid, prompt_toolkit) are far lower-level. | HIGH |
| rich | >=14.0.0 | Terminal formatting (used by Textual internally and CLI output) | Already a dependency. Textual depends on Rich. Also used standalone for CLI table/panel output. | HIGH |

**Critical pattern for TUI + WebSocket:** Use `self.run_worker(coroutine, exclusive=True)` for the WebSocket connection loop. The codebase already does this correctly in `YigthinkerTUI.on_mount()`. Use `self.call_from_thread()` if any thread workers need to update the UI. Use `self.post_message()` from the WebSocket callback to push updates into Textual's message queue — this is thread-safe.

### Session Hibernation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pyarrow | >=23.0.0 | Parquet serialization for DataFrame hibernation | Already in codebase. PyArrow 23.0.1 (Feb 2026) is current. Parquet is the right format for DataFrame persistence — columnar, compressed, typed, cross-platform. The codebase uses Snappy compression which is correct for this use case (fast decompression, moderate compression ratio). Zstd would save ~30% more space but adds decompression latency — unnecessary for local session files. | HIGH |
| pickle (stdlib) | N/A | Fallback serialization for non-DataFrame vars | Already in codebase as fallback when PyArrow cannot handle mixed-type columns. Pickle protocol 5 (used) is correct for Python 3.11+. The security concern is mitigated because hibernation files are local, not user-uploaded. | HIGH |

**Compression recommendation:** Keep Snappy. The hibernation files are ephemeral local caches, not long-term storage. Decompression speed matters more than file size. The codebase's `_save_var` / `_load_var` pattern with Parquet-primary, pickle-fallback is sound.

### Channel Adapters

#### Feishu/Lark

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| lark-oapi | >=1.5.0 | Official Feishu/Lark SDK | Already chosen. This is the official SDK from Larksuite (`larksuite/oapi-sdk-python`). v1.5.3 is the current release. Provides typed API clients for IM (send/update messages), event callbacks, signature verification. The alternative `feishu-cc` is a community wrapper — use the official SDK. | HIGH |

**Critical constraint — Feishu webhook timeout:** Feishu gives 3-5 seconds for webhook response (the exact timeout varies by documentation version; 3s is the conservative safe threshold). The codebase correctly implements immediate ACK + `asyncio.create_task()` for background processing. The "thinking card" pattern (send placeholder card -> process -> PATCH card with result) is the standard Feishu bot UX.

**Event deduplication:** The codebase uses SQLite-backed dedup (via `EventDeduplicator`), which is correct. Feishu retries up to 3 times for failed webhooks. In-memory dedup would lose state on restart. SQLite is the right choice — aiosqlite is already a dependency.

#### Microsoft Teams

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | >=0.28.0 | HTTP client for Teams Graph API calls | Already a core dependency (used by Ollama provider too). Async-native, HTTP/2 support. The codebase correctly avoids the deprecated `botbuilder-core` SDK. | HIGH |
| msal | >=1.35.0 | Azure AD token acquisition | Already chosen. MSAL 1.35.1 (Mar 2026) is current. This is Microsoft's official auth library. `ConfidentialClientApplication` for service-to-service token flow. No alternatives — this is the only supported path for Azure AD. | HIGH |

**Teams adapter approach — VALIDATE WITH CAUTION:** The codebase uses Outgoing Webhooks, which has significant limitations:
- Scoped to a single Team (cannot be installed org-wide)
- 5-second synchronous response timeout (not configurable)
- Cannot proactively message users (response-only)
- Not supported in private channels
- Requires HMAC-SHA256 signature verification

The alternative is a proper Bot registration via Azure Bot Service + Microsoft 365 Agents SDK (successor to Bot Framework). The Agents SDK now has a Python preview. However, for a v1 implementation, Outgoing Webhooks are simpler and sufficient. Flag for future upgrade if Teams adoption grows.

**Microsoft ecosystem status (2026):** Office 365 Connectors are deprecated (retirement deadline extended to March 31, 2026). The Agents Toolkit (formerly Teams Toolkit) is the official development path going forward. The `botbuilder-core` deprecation decision in the codebase is correct — the new Microsoft 365 Agents SDK is the replacement, but it is still in Python preview. Using raw `httpx` + `msal` is the pragmatic middle ground.

| Confidence | MEDIUM — Outgoing Webhooks work but have real limitations. Monitor Microsoft 365 Agents SDK Python GA timeline. |

#### Google Chat

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| google-api-python-client | >=2.190.0 | Google Chat API access | Already chosen. v2.193.0 (Mar 2026) is current. Released weekly by Google. This is the official discovery-based API client. Use `build('chat', 'v1', credentials=...)` for the Chat API. | HIGH |
| google-auth | >=2.49.0 | Service account authentication | Already chosen. Required for server-to-server auth. `google.oauth2.service_account.Credentials.from_service_account_file()` is the standard pattern. | HIGH |

**Google Chat constraint:** Webhook responses must complete synchronously (30s timeout). The codebase uses `asyncio.wait_for(..., timeout=25.0)` as a safety margin, which is correct. Per-space rate limiting via `asyncio.Semaphore(1)` handles the 1 req/s/space limit. Cards v2 for rich responses. This adapter is simpler than Feishu because there is no async card update pattern — it is pure request-response.

### Session Memory & Auto Dream

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| filelock | >=3.25.0 | Prevent concurrent Auto Dream runs | Already a dependency. FileLock with `timeout=0` (non-blocking) is the correct pattern — if another dream is running, skip this one. Cross-platform (works on Windows). | HIGH |
| JSONL (stdlib json) | N/A | Session transcript storage, memory extraction source | Already used. JSONL is the right format for append-only session logs — one JSON object per line, streamable, partial-read friendly. No external dependency needed. | HIGH |
| Markdown (plain text) | N/A | MEMORY.md storage format | Already used. The MemoryManager stores extracted knowledge as structured Markdown. This is human-readable, diff-friendly, and can be injected directly into LLM context. No vector database needed at this scale — keyword/heading-based retrieval is sufficient for per-project memory. | MEDIUM |

**No vector store recommendation:** The Session Memory design stores knowledge in structured Markdown files (MEMORY.md) with section headers. For a financial analysis agent with project-scoped memory, this is appropriate. The total memory per project will be small (kilobytes, not megabytes). Vector stores (Chroma, Qdrant, pgvector) add operational complexity without proportional benefit at this scale. Re-evaluate if memory exceeds ~50KB per project or if semantic search becomes necessary.

**Auto Dream implementation gap:** The current `AutoDream._do_dream()` has a placeholder comment "In a full implementation: spawn subagent to consolidate sessions." This needs to use the `AgentLoop.run()` with a consolidation prompt against the session transcripts. The technology stack for this is already present (LLM provider + JSONL reader + file I/O) — no new dependencies needed.

### Testing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pytest | >=9.0.0 | Test runner | Already installed. v9.0.2 in venv. Standard choice. | HIGH |
| pytest-asyncio | >=1.0.0 | Async test support | **CRITICAL VERSION ISSUE.** The codebase has v1.3.0 installed but `pyproject.toml` pins `>=0.23.0`. pytest-asyncio 1.0.0 (May 2025) introduced **breaking changes**: the `event_loop` fixture was removed, `loop_scope` semantics changed. The installed v1.3.0 works, but the `>=0.23.0` floor version in pyproject.toml would allow installing pre-1.0 versions that are incompatible with the test code. **Pin to `>=1.0.0`**. | HIGH |
| pytest-mock | >=3.15.0 | Mocking helpers | Already installed. Standard choice. | HIGH |

### Infrastructure / Dev Tooling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| hatchling | (build-time) | Build backend | Already configured. Modern PEP 517 build backend. Fine for this project. | HIGH |
| aiosqlite | >=0.22.0 | Async SQLite for Feishu event dedup + default DB | Already a dependency. Wraps sqlite3 stdlib in async interface. Used both for tool SQL queries and for the Feishu dedup store. | HIGH |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Gateway server | FastAPI + uvicorn | Litestar, Sanic, aiohttp | FastAPI is already implemented, has the largest ecosystem, best documentation. No reason to switch. |
| TUI framework | Textual | prompt_toolkit, urwid, blessed | Textual is the only framework with CSS-like layouts, widget composition, screens, workers, and async support. The others require significantly more boilerplate for the same UX. |
| WS client (TUI) | websockets | aiohttp ws, httpx (no ws) | websockets is purpose-built, smaller, simpler API. aiohttp is heavier. httpx does not support WebSocket. |
| DataFrame serialization | Parquet (pyarrow) | Feather, CSV, HDF5 | Parquet: columnar, compressed, typed, universal. Feather is faster but less compressed. CSV loses types. HDF5 requires h5py. |
| Feishu SDK | lark-oapi | feishu-cc, raw HTTP | lark-oapi is the official SDK. Community wrappers lag behind API updates. |
| Teams auth | msal | azure-identity | msal is the lower-level library that azure-identity wraps. For ConfidentialClient flows, msal is more direct and has fewer transitive deps. |
| Teams integration | Outgoing Webhook + httpx | Microsoft 365 Agents SDK (Python preview) | Agents SDK is still preview for Python. Outgoing Webhooks are simpler for v1. Upgrade path exists. |
| Session memory | Markdown files | Vector store (Chroma, Qdrant) | Overkill for per-project knowledge at KB scale. Adds operational deps. Re-evaluate at 50KB+ per project. |
| Memory locking | filelock | Redis lock, DB advisory lock | filelock is zero-dependency, cross-platform, already installed. Redis/DB locks require infrastructure. |

## Version Pinning Issues Found

The `pyproject.toml` version floors are too loose in several places. These will not cause immediate problems (the venv has correct versions) but could cause failures on fresh installs:

| Package | Current Pin | Installed | Recommended Pin | Issue |
|---------|-------------|-----------|-----------------|-------|
| pytest-asyncio | >=0.23.0 | 1.3.0 | >=1.0.0 | v1.0 removed `event_loop` fixture. Pre-1.0 installs would break tests. |
| fastapi | >=0.111.0 | 0.135.3 | >=0.130.0 | SSE support and Starlette >=0.46.0 were added in 0.130+. Pin higher to get these. |
| textual | >=0.80.0 | 8.2.1 | >=8.0.0 | Textual 8.x is a major version jump from 0.x. The `>=0.80.0` pin would allow installing ancient Textual versions. |
| websockets | >=12.0 | 16.0 | >=15.0 | v15+ dropped Python 3.9, added max_size improvements. Pin to >=15.0 for consistency. |
| pyarrow | >=15.0.0 | 23.0.1 | >=20.0.0 | PyArrow 20+ has better pandas 3.x integration. Pin higher. |

## Installation

```bash
# Core (Agent Loop + CLI)
pip install -e .

# Development
pip install -e ".[dev]"

# Gateway daemon
pip install -e ".[gateway]"

# TUI client
pip install -e ".[tui]"

# All channels
pip install -e ".[gateway,feishu,teams,gchat]"

# Everything
pip install -e ".[dev,forecast,dashboard,gateway,tui,feishu,teams,gchat]"

# Shorthand for all channels
pip install -e ".[all-channels]"
```

## Platform-Specific Notes

### Windows (primary dev platform)

- **uvloop is not available on Windows.** uvicorn will use the default asyncio event loop. This is fine for development. In production on Linux, install `uvicorn[standard]` to get uvloop for ~2x throughput.
- **No `fork()` on Windows.** The Gateway cannot daemonize. Use `--fg` (foreground) mode or run as a Windows Service. The codebase already accounts for this.
- **`asyncio.Lock()` in `ManagedSession`** is correctly used (not `threading.Lock`). All session access goes through the async lock, which works on Windows asyncio.
- **filelock** works correctly on Windows (uses `msvcrt.locking()`).

### Linux/macOS (production)

- Install `uvicorn[standard]` for uvloop + httptools.
- Gateway can run behind a reverse proxy (nginx) for TLS termination and load balancing.
- Single uvicorn worker is recommended because sessions live in-process memory. Multi-worker would require Redis-backed session registry.

## Dependencies NOT to Add

| Library | Why NOT |
|---------|---------|
| `redis` / `aioredis` | Sessions are in-process. Redis adds infrastructure complexity. Only needed if scaling to multi-worker or multi-node. |
| `celery` / `dramatiq` | Background task queues. Overkill — `asyncio.create_task()` handles Feishu async processing. |
| `botbuilder-core` | Deprecated Microsoft Teams SDK. Already correctly avoided. |
| `chroma` / `qdrant-client` | Vector stores. Memory scale is too small to justify. |
| `sqlmodel` | SQLAlchemy + Pydantic wrapper. Already using both separately; SQLModel adds no value here. |
| `apscheduler` | Task scheduling. Explicitly out of scope for this milestone. |
| `polars` | DataFrame alternative. The codebase is pandas-native. Adding polars creates a dual-library burden. |
| `msgpack` / `protobuf` | Binary serialization for WebSocket messages. JSON is fine for the message volume (human-speed chat). Premature optimization. |

## Sources

- [FastAPI releases](https://github.com/fastapi/fastapi/releases) — v0.135.1, Apr 2026
- [FastAPI WebSocket docs](https://fastapi.tiangolo.com/advanced/websockets/)
- [FastAPI SSE/streaming](https://jetbi.com/blog/streaming-architecture-2026-beyond-websockets)
- [Textual PyPI](https://pypi.org/project/textual/) — v8.2.1, Mar 2026
- [Textual Workers guide](https://textual.textualize.io/guide/workers/)
- [websockets PyPI](https://pypi.org/project/websockets/) — v16.0, Jan 2026
- [websockets docs](https://websockets.readthedocs.io/)
- [PyArrow install docs](https://arrow.apache.org/docs/python/install.html) — v23.0.1, Feb 2026
- [PyArrow Parquet guide](https://arrow.apache.org/docs/python/parquet.html)
- [Snappy vs Zstd for Parquet](https://dev.to/ldsands/snappy-vs-zstd-for-parquet-in-pyarrow-9g0)
- [lark-oapi PyPI](https://pypi.org/project/lark-oapi/) — v1.5.3
- [lark-oapi GitHub](https://github.com/larksuite/oapi-sdk-python)
- [Feishu callback handling](https://open.feishu.cn/document/server-side-sdk/python--sdk/handle-callbacks)
- [MSAL Python PyPI](https://pypi.org/project/msal/) — v1.35.1, Mar 2026
- [MSAL Python docs](https://learn.microsoft.com/en-us/entra/msal/python/)
- [Teams Outgoing Webhooks](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-outgoing-webhook)
- [Teams SDK landscape 2025](https://www.voitanos.io/blog/microsoft-teams-sdk-evolution-2025/)
- [Microsoft 365 Agents SDK](https://github.com/microsoft/Agents)
- [Office 365 Connectors retirement](https://devblogs.microsoft.com/microsoft365dev/retirement-of-office-365-connectors-within-microsoft-teams/)
- [google-api-python-client PyPI](https://pypi.org/project/google-api-python-client/) — v2.193.0, Mar 2026
- [Google Chat webhook quickstart](https://developers.google.com/workspace/chat/quickstart/webhooks)
- [Google Chat Cards v2](https://developers.google.com/workspace/chat/create-update-interactive-cards)
- [pytest-asyncio releases](https://github.com/pytest-dev/pytest-asyncio/releases) — v1.3.0, Nov 2025
- [pytest-asyncio 1.0 migration](https://thinhdanggroup.github.io/pytest-asyncio-v1-migrate/)
- [uvicorn PyPI](https://pypi.org/project/uvicorn/) — v0.42.0, Mar 2026
- [httpx PyPI](https://pypi.org/project/httpx/) — v0.28.1
- [AI agent cross-session memory patterns](https://towardsdatascience.com/ai-agent-with-multi-session-memory/)
- [Persistent memory for AI coding agents](https://medium.com/@sourabh.node/persistent-memory-for-ai-coding-agents-an-engineering-blueprint-for-cross-session-continuity-999136960877)
- [WebSocket best practices for FastAPI](https://websocket.org/guides/frameworks/fastapi/)
