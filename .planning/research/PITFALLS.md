# Pitfalls Research

**Domain:** Multi-channel AI agent gateway with Textual TUI, session hibernation, and messaging platform webhooks
**Researched:** 2026-04-02
**Confidence:** HIGH (based on codebase analysis + verified community/official patterns)

## Critical Pitfalls

### Pitfall 1: Fire-and-Forget `asyncio.create_task()` Gets Garbage Collected

**What goes wrong:**
Background tasks created with `asyncio.create_task()` silently disappear mid-execution. In the Feishu adapter, `asyncio.create_task(self._process_event(body))` on line 89 creates a task to process a webhook event in the background, but no reference is stored. Python's event loop holds only a weak reference to tasks. If garbage collection runs before the task completes, the task vanishes -- the user's message is swallowed with zero indication of failure.

**Why it happens:**
Developers assume `create_task()` works like launching a thread. Unlike threads, asyncio tasks are garbage-collected if no strong reference exists. This has become more aggressive in Python 3.12+. The Python docs warn about it, but it is easy to miss in "fire-and-forget" webhook patterns where you intentionally do not `await` the task.

**How to avoid:**
Maintain a `set()` of background tasks at the adapter or gateway level:
```python
self._background_tasks: set[asyncio.Task] = set()

task = asyncio.create_task(self._process_event(body))
self._background_tasks.add(task)
task.add_done_callback(self._background_tasks.discard)
```
This is the pattern recommended in the official Python asyncio documentation.

**Warning signs:**
- Feishu messages sporadically "disappear" with no error log
- The `_process_event` exception handler never fires even for known-bad inputs
- Problem appears randomly and is harder to reproduce under debugger (GC timing changes)

**Phase to address:**
Phase 1 (Agent Loop + Core fixes) -- this is a data-loss bug that exists today in the Feishu adapter. Must be fixed before any channel testing.

---

### Pitfall 2: Nested `asyncio.run()` Silently Breaks MCP Loading in Gateway Context

**What goes wrong:**
`_build()` calls `asyncio.run(MCPLoader(...).load())` on line 60 of `__main__.py`. When the gateway's `GatewayServer.start()` calls `_build()`, it is already inside a running event loop (uvicorn's). `asyncio.run()` cannot be called from within a running event loop -- it raises `RuntimeError: This event loop is already running`. The `except ModuleNotFoundError: pass` on line 61 does not catch `RuntimeError`, so the exception propagates and kills MCP loading. MCP tools silently fail to register.

**Why it happens:**
`_build()` was written for CLI-first usage (where no event loop exists yet), then reused by the gateway (where uvicorn provides the event loop). This is a classic "sync/async boundary mismatch" that occurs when code is shared between sync CLI entry points and async server contexts.

**How to avoid:**
Extract `_build()` into `yigthinker/builder.py`. Make MCP loading awaitable:
```python
async def _build_async(settings: dict) -> tuple[AgentLoop, ConnectionPool]:
    ...
    if mcp_config.exists():
        await MCPLoader(mcp_json_path=mcp_config, registry=tools).load()
    ...

def _build_sync(settings: dict) -> tuple[AgentLoop, ConnectionPool]:
    # For CLI usage only
    ...
    if mcp_config.exists():
        asyncio.run(MCPLoader(...).load())
    ...
```
Never use `asyncio.run()` inside code that might run under an existing event loop. Never use `nest_asyncio` as a workaround -- it masks architectural problems and causes subtle reentrancy bugs.

**Warning signs:**
- MCP tools work in CLI REPL but not through the gateway
- `ModuleNotFoundError` catch silently swallowing `RuntimeError` (wrong exception type)
- Gateway `_build()` completes but `tools` registry is missing MCP-provided tools

**Phase to address:**
Phase 1 (Agent Loop) -- `_build()` extraction is a prerequisite for gateway correctness.

---

### Pitfall 3: Shared `PermissionSystem` Causes Cross-Session Permission Escalation

**What goes wrong:**
`_build()` creates a single `PermissionSystem` instance. All gateway sessions share it. When `AgentLoop` handles an `ALLOW_ALL` response from one user, it calls `self._permissions._allow.append(tool_name)`, mutating the shared list. A user in session A who grants `ALLOW_ALL` for `sql_query` inadvertently grants it for all users in all sessions on that gateway. This is a privilege escalation vulnerability.

**Why it happens:**
The CLI has a single user and single session, so a shared `PermissionSystem` was correct. The gateway reuses `_build()` which creates one `PermissionSystem` per process, not per session. Runtime mutation of `_allow` via direct list append (rather than through a method with session scoping) makes the contamination invisible.

**How to avoid:**
- Make `PermissionSystem` immutable after construction (frozen base policy)
- Add session-scoped permission overrides: `PermissionSystem.allow_for_session(tool_name, session_id)`
- Never mutate `_allow`/`_deny` lists directly from `AgentLoop`; use a method that validates scope
- Alternative: Create per-session `PermissionSystem` clones from the base config

**Warning signs:**
- In gateway testing: user B can call tools that only user A approved
- `PermissionSystem._allow` list grows monotonically across sessions
- No permission prompts for tools that should require approval

**Phase to address:**
Phase 2 (Gateway) -- must be fixed before multi-user gateway deployment. Write a specific test for cross-session contamination.

---

### Pitfall 4: Teams Webhook Handler Blocks Until Agent Completes (No Async ACK)

**What goes wrong:**
The Teams adapter's webhook handler on line 60-91 of `teams/adapter.py` calls `await self._gateway.handle_message(...)` synchronously within the HTTP response cycle. If the agent takes 30+ seconds (LLM call + tool execution + multiple turns), the webhook caller (Microsoft Teams) times out. Teams' outgoing webhook timeout is approximately 10 seconds. The user gets an error card from Teams, and then when the gateway eventually responds, the HTTP connection is already dead.

Additionally, the Teams webhook has no HMAC signature verification (line 64-65 has a comment `# Verify HMAC signature if configured` but no implementation). Any HTTP client can POST to `/webhook/teams` and inject messages into agent sessions.

**Why it happens:**
The Feishu adapter correctly uses the fire-and-forget pattern (ACK immediately, process in background, update card). The Teams adapter was not built with the same pattern, likely because Teams outgoing webhooks expect a synchronous response. But when the agent is slow, the synchronous pattern fails.

**How to avoid:**
For Teams: Use the "proactive messaging" pattern via Graph API. ACK with a "processing..." card, then PATCH the result asynchronously. This requires the bot to have proper App registration (not just outgoing webhook), which changes the Teams integration model.

For HMAC: Implement HMAC-SHA256 verification using `hmac.compare_digest()`. Note the Teams-specific gotcha: the HMAC key must be decoded as base64, and the signature is in the `Authorization` header (not a custom header). The token uses UTF-16LE encoding for the key bytes.

**Warning signs:**
- Teams users see timeout errors for any non-trivial query
- Gateway logs show completed responses with no corresponding webhook delivery
- Spiking response times in `/webhook/teams` endpoint metrics

**Phase to address:**
Phase 4 (Channels) -- Teams adapter needs architectural rework from synchronous to async response pattern. HMAC verification is a security prerequisite before any Teams deployment.

---

### Pitfall 5: Textual TUI `_on_ws_message` Callback Invoked from Wrong Thread

**What goes wrong:**
`GatewayWSClient._read_loop()` dispatches received messages via `self._on_message(data)`. This callback is `YigthinkerTUI._on_ws_message()`, which directly calls `self._chat_log.append_response()`, `self._vars_panel.update_vars()`, and other widget methods. Textual apps are not thread-safe. If the WebSocket read loop runs in a worker thread (via `run_worker` with a threaded worker, or if `websockets` internally uses threads), these calls modify widgets from the wrong thread, causing race conditions, visual glitches, or crashes.

The current code uses `self.run_worker(self._ws_client.connect_loop(), exclusive=True)` which runs as an async worker (not a thread worker), so it should be on the same event loop. However, the `websockets` library's internal behavior and Textual's worker execution model can interact in surprising ways, especially during reconnection (where the worker is recreated).

**Why it happens:**
Developers wire callbacks that modify UI state without considering which thread/task they execute on. In Textual, only `post_message()` is thread-safe. All other widget modifications must happen on the main thread. The async worker approach is safer than a thread worker, but reconnection logic (creating new `websockets.connect()` contexts) and Textual's exclusive worker lifecycle introduce edge cases.

**How to avoid:**
- Use `post_message()` from the WebSocket callback instead of direct widget manipulation:
```python
def _on_ws_message(self, data: dict[str, Any]) -> None:
    self.post_message(WSDataReceived(data))  # Custom message, thread-safe
```
- Handle `WSDataReceived` in an `on_ws_data_received` handler which runs on the main thread
- Never call `query_one()`, `append()`, or set reactive attributes from a callback that might not be on the main thread

**Warning signs:**
- TUI shows garbled output or partial renders after receiving gateway messages
- Intermittent `NoMatches` exceptions from `query_one()` during widget updates
- TUI crashes during WebSocket reconnection with stack traces in Textual internals
- Issues appear sporadically and vanish when debugging (the Heisenbug pattern)

**Phase to address:**
Phase 3 (TUI) -- must be addressed as the TUI architecture is built, before wiring real WebSocket communication.

---

### Pitfall 6: Session Hibernation Deletes Files Before Confirming Successful Restore

**What goes wrong:**
`SessionHibernator.load()` on line 149 calls `_rmtree(session_dir)` after loading the session into memory. If the process crashes between the `_rmtree()` and the caller adding the session to `SessionRegistry._sessions`, the hibernated data is gone and the in-memory session is lost. Data loss with no recovery path.

Additionally, `_save_var()` is synchronous and called from `async def save()` without `asyncio.to_thread()`. Writing large DataFrames to Parquet blocks the event loop, freezing the entire gateway during hibernation.

**Why it happens:**
The "load then delete" pattern is convenient but not crash-safe. Production session stores need a "restore, verify, then delete" pattern (similar to write-ahead logs or two-phase commit). The sync-in-async issue is a common pitfall when wrapping existing sync code in `async def` without actually making the I/O non-blocking.

**How to avoid:**
- Do not delete hibernation files in `load()`. Instead:
  1. Restore session into memory
  2. Add to `SessionRegistry._sessions`
  3. Mark the hibernation directory as "restored" (e.g., rename to `.restored/`)
  4. Clean up `.restored/` directories in a periodic background task
- Wrap `_save_var()` calls in `await asyncio.to_thread()`:
```python
for name, value in session.ctx.vars._vars.items():
    entry = await asyncio.to_thread(_save_var, name, value, vars_dir)
    manifest[name] = entry
```

**Warning signs:**
- Gateway crash during restore leaves sessions permanently lost
- Gateway freezes for seconds during idle-session eviction (observable via `/health` latency spikes)
- Parquet writes for 1M+ row DataFrames block all WebSocket and webhook traffic

**Phase to address:**
Phase 2 (Gateway) -- hibernation correctness is a gateway reliability requirement. The crash-safety fix must happen before production use.

---

### Pitfall 7: Feishu 3-Second ACK Race Condition with Event Deduplication

**What goes wrong:**
The Feishu adapter records the event ID in the deduplicator *before* launching the background task (line 86), then immediately returns the ACK (line 90). If the gateway crashes after recording the event but before `_process_event` completes, the event is marked as "seen" in SQLite. When Feishu re-delivers the event (at-least-once semantics), the deduplicator rejects it as a duplicate. The user's message is permanently lost.

Additionally, `EventDeduplicator` uses `sqlite3.Connection` created in `__init__` without `check_same_thread=False`. If uvicorn uses multiple threads to dispatch webhook callbacks (e.g., with `--workers > 1` or thread pool executors), SQLite operations will raise `ProgrammingError`.

**Why it happens:**
The dedup-then-process ordering prioritizes avoiding double-processing over ensuring at-least-once delivery. This is a classic distributed systems tradeoff. The correct choice for a messaging system is to prefer double-processing (idempotent) over data loss.

**How to avoid:**
- Record the event in dedup *after* successful processing, or use a two-phase approach:
  1. Record with status `"processing"` before ACK
  2. Update to `"done"` after successful processing
  3. On re-delivery: if status is `"processing"` for > N seconds, retry (the previous attempt likely crashed)
- Use `aiosqlite` instead of `sqlite3` for async-safe database access, or at minimum `check_same_thread=False` with a `threading.Lock`

**Warning signs:**
- Feishu users report messages that "disappear" after gateway restarts
- Dedup SQLite table grows with entries that have no corresponding agent response
- `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` in logs

**Phase to address:**
Phase 4 (Channels) -- the dedup strategy must be redesigned when implementing Feishu adapter properly. The SQLite thread-safety fix is needed in Phase 2 if the gateway runs with multiple workers.

---

### Pitfall 8: `ManagedSession.lock` Serializes All Per-Session Operations Including Reads

**What goes wrong:**
A single `asyncio.Lock` per session serializes every operation: user messages, vars list, session info, webhook callbacks. When an LLM call takes 15-30 seconds (normal for complex tool-use chains), all other requests for that session queue behind it. For the TUI: vars panel updates, session info requests, and even new user messages all block. For webhooks: the Feishu "thinking..." card cannot be sent because `handle_message` is already holding the lock for a previous message.

**Why it happens:**
A single lock is the simplest concurrency model and is correct for preventing concurrent agent loop execution. But using the same lock for read operations (listing vars, getting session info) is unnecessary and creates artificial contention.

**How to avoid:**
- Use `asyncio.Lock` only for agent loop execution (write path)
- Allow lock-free reads for: `vars.list()`, `session.to_info()`, session list
- Consider a read-write lock pattern: multiple concurrent readers, exclusive writer
- For the TUI: send vars updates as a side-effect of the agent loop (inside the lock), not as a separate locked operation

**Warning signs:**
- TUI vars panel shows stale data during long agent turns
- `/api/sessions` endpoint times out during active agent execution
- Webhook responses queue up behind each other for the same session
- Feishu "thinking..." card never appears because the lock is already held

**Phase to address:**
Phase 2 (Gateway) -- the lock strategy should be refined when implementing real multi-client session access.

---

### Pitfall 9: Google Chat Adapter Blocks Webhook Response for Full Agent Execution

**What goes wrong:**
The Google Chat adapter on line 69 does `await asyncio.wait_for(self._gateway.handle_message(...), timeout=25.0)`. This means the webhook HTTP response is held open for up to 25 seconds while the agent processes. Google Chat's webhook timeout is approximately 30 seconds. This barely works for simple queries but fails for multi-turn tool chains. Meanwhile, the `asyncio.Semaphore(1)` per space means only one message per space can be processed at a time. If two users in the same space send messages, the second waits for the first to complete (up to 25 seconds).

**Why it happens:**
Google Chat webhooks genuinely expect a synchronous response (unlike Feishu which supports async card updates). The adapter correctly uses `wait_for` with a timeout, but the timeout is set too close to the platform limit, leaving no margin. The per-space semaphore is well-intentioned (Google Chat enforces 1 req/sec per space for outbound messages) but is used for the inbound processing path where it creates artificial serialization.

**How to avoid:**
- Use Google Chat's async messaging API: return a minimal ACK, then send the full response via `spaces.messages.create` API call
- Separate the inbound rate limit (webhook processing) from the outbound rate limit (API calls to Google Chat)
- Set `wait_for` timeout to 15 seconds (leaving 15 seconds of margin for network latency)
- For timeout cases: queue the request and send the response asynchronously when available

**Warning signs:**
- Google Chat users see "Analysis is taking longer than expected" for routine queries
- Second user in a space waits 25+ seconds for first user's query to finish
- Webhook timeout errors in Google Chat admin console

**Phase to address:**
Phase 4 (Channels) -- Google Chat adapter needs the same async pattern as Feishu.

---

### Pitfall 10: `_build()` Shared Between `__main__.py` and Gateway Creates Circular Import Risk

**What goes wrong:**
`GatewayServer.start()` imports `from yigthinker.__main__ import _build`. This creates a dependency from a library module (`gateway/server.py`) to the CLI entry point (`__main__.py`). This is an anti-pattern that causes: (a) circular import risk if `__main__` imports gateway modules at module level, (b) inability to use the gateway without the CLI module, (c) test fragility since `__main__` imports `typer`, `rich`, and other CLI-only dependencies.

**Why it happens:**
`_build()` grew organically as the "build everything" function in the CLI entry point. When the gateway needed the same setup, the quickest path was to import it. This is a common brownfield pattern where shared logic lives in the wrong module.

**How to avoid:**
Extract `_build()` into `yigthinker/builder.py`:
```python
# yigthinker/builder.py
def build_agent(settings: dict) -> tuple[AgentLoop, ConnectionPool]:
    ...
```
Both `__main__.py` and `gateway/server.py` import from `builder.py`. The builder module has no CLI dependencies.

**Warning signs:**
- `ImportError` when running gateway in isolation (without CLI deps)
- Circular import errors when adding new imports to `__main__.py`
- Gateway tests that unexpectedly require `typer` and `rich`

**Phase to address:**
Phase 1 (Agent Loop) -- `_build()` extraction is a low-risk refactor that unblocks clean gateway development.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Chart tools bypass `VarRegistry.set()` via `ctx.vars._vars[name] = value` | Charts stored without type checking | Any VarRegistry refactor (eviction, size limits, type enforcement) silently breaks charts; hibernation round-trip is untested | Never -- extend VarRegistry to support artifact types |
| `ContextManager()` instantiated per tool call with default 200K tokens | Each tool works independently | Token budget customization ignored; no shared state across tools in one turn; unnecessary object creation overhead | Only in Phase 1 MVP; must inject via SessionContext before Phase 2 |
| `_schedule_hibernate` falls back to `asyncio.run()` when no loop exists | LRU eviction works in both sync and async contexts | Blocks the thread; creates a second event loop if called from a thread pool; masking an architectural gap | Never in production -- eviction should always run in the gateway's event loop |
| Pickle fallback in hibernation for non-DataFrame/non-string vars | Any Python object can be hibernated | Pickle is insecure (arbitrary code execution on load), version-fragile, and non-portable; pickled objects may fail to deserialize after code changes | Only for development; production must whitelist serializable types |
| Stubs that report success (`auto_dream`, `spawn_agent`, `report_schedule`) | LLM can "use" the tool without errors | LLM plans around capabilities that do not exist; users believe features work when they do not; auto_dream burns its threshold without producing value | Never -- stubs must return clear error messages or be gated behind feature flags |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Feishu/Lark webhook | Using `lark` (international) domain when app is configured for `feishu.cn` domain, or vice versa. The API endpoints differ. | Check `app_id` prefix or explicit `domain` config to route to correct API base URL |
| Feishu card update | Calling `PATCH` on a card that was sent as a regular message (not interactive card) -- Feishu only supports updating interactive cards | Always send the initial "thinking..." message as `msg_type="interactive"` |
| Teams HMAC verification | Using UTF-8 encoding for the HMAC key. Teams uses the base64-decoded security token as the HMAC-SHA256 key, not the raw string | `key = base64.b64decode(security_token)` then `hmac.new(key, body_bytes, hashlib.sha256)` |
| Teams outgoing webhook | Expecting to send async replies. Teams outgoing webhooks require the response in the HTTP response body -- there is no callback URL | Use proper Bot registration (Azure Bot Service) for async messaging, or accept the synchronous constraint |
| Google Chat | Not handling the `ADDED_TO_SPACE` event type, causing the bot to appear unresponsive when first added | Return a welcome text for `ADDED_TO_SPACE`; only process `MESSAGE` events for agent queries |
| Google Chat rate limit | Applying per-space rate limits to inbound processing instead of outbound API calls | Rate-limit outbound `spaces.messages.create` calls; process inbound webhook requests as fast as possible |
| WebSocket reconnection | Sending messages during the reconnection window before auth completes | Queue messages during reconnect; flush after successful auth + session attach |
| SQLite dedup in async context | Using `sqlite3` module from async code without thread safety (`check_same_thread=False`) | Use `aiosqlite` or wrap all SQLite operations in `asyncio.to_thread()` |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous `exec()` in `df_transform` blocks event loop | All WebSocket clients freeze during pandas operations; webhook ACKs delayed | Wrap in `await asyncio.to_thread(exec, ...)` | Any DataFrame operation > 100ms (10K+ rows with complex transforms) |
| Synchronous Parquet writes in hibernation | Gateway unresponsive during session eviction; `/health` returns 503 | `await asyncio.to_thread(_save_var, ...)` for each variable | DataFrames > 100MB; multiple sessions hibernating simultaneously |
| PDF report `df.values.tolist()` doubles memory | OOM kill on large DataFrames; gateway process crashes | Add row-count guard (max 10K rows for PDF); suggest CSV for large exports | DataFrames > 500K rows |
| Single `AgentLoop` instance + LLM API rate limits | HTTP 429 errors from LLM provider; cascading timeouts across sessions | Per-session `AgentLoop` instances or async worker pool with backpressure and rate-limit awareness | > 5 concurrent active sessions with the same LLM provider |
| `_ws_clients` list scanned linearly for broadcasts | Broadcast latency grows with connected client count | Use a dict keyed by session_key for O(1) lookup | > 50 concurrent TUI connections |
| `list_sessions()` sorts all sessions on every call | API response time degrades with session count | Cache the sorted list; invalidate on session create/remove | > 500 active sessions |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No HMAC on Teams webhook | Any HTTP client can inject messages into agent sessions via `/webhook/teams` | Implement HMAC-SHA256 verification with `hmac.compare_digest()` before processing any Teams event |
| `df_transform` sandbox allows `type` builtin | `type(df).__mro__[-1].__subclasses__()` chain reaches unrestricted builtins; full sandbox escape | Remove `type` from `_SAFE_BUILTINS`; add `__class__`, `__mro__`, `__subclasses__` to AST blocker |
| Pickle deserialization in hibernation restore | Malicious pickle file in `~/.yigthinker/hibernate/` executes arbitrary code on restore | Whitelist allowed types; use `restricted_loads` or replace pickle with JSON/msgpack for non-DataFrame vars |
| API keys in plaintext `settings.json` | Key exfiltration via file access; keys visible in process memory via `/proc` | Use `keyring` library for OS-native credential storage; never serialize keys to disk |
| Gateway token file not protected on Windows | `os.chmod(0o600)` silently fails on Windows; token readable by all local users | Use `icacls` on Windows or document the limitation; generate per-session tokens with expiry |
| WebSocket accepts before checking auth state race | Between `ws.accept()` and the auth check, malicious clients could send messages | Parse auth message before accepting, or implement a message queue that discards pre-auth messages |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No streaming output in TUI | User stares at blank screen for 10-30 seconds during LLM response; assumes app crashed | Implement `TokenStreamMsg` protocol; display tokens as they arrive; show "thinking..." indicator |
| Stubs return success messages | User believes `report_schedule` created a real schedule; `auto_dream` claims memory was consolidated | Return explicit "This feature is not yet available" error; remove from tool descriptions or mark `(preview)` |
| Feishu "thinking..." card appears after result | Race condition if agent responds very quickly: "thinking..." card POST has not returned before result card PATCH fires | Check `thinking_msg_id` before PATCH; if None, send result as new message |
| VarRegistry.list() hides chart variables | TUI vars panel never shows charts; user cannot reference chart names | Extend `VarRegistry.list()` to include non-DataFrame artifacts with type metadata |
| Session resume drops tool call history | Resumed session has gaps; LLM re-executes previously completed tool calls, wasting API credits | Properly serialize/deserialize tool_use and tool_result message blocks in JSONL transcript |
| Silent Prophet fallback to ExponentialSmoothing | User requests Prophet forecast, gets a different algorithm with no notice | Error clearly when Prophet is requested but not installed; make fallback explicit in tool result |

## "Looks Done But Isn't" Checklist

- [ ] **Feishu adapter:** Has webhook endpoint and ACK pattern but background task references are not stored -- tasks can be garbage collected
- [ ] **Teams adapter:** Has webhook endpoint but no HMAC verification and no async response pattern -- will timeout on real queries
- [ ] **Session hibernation:** Has save/load but deletes hibernation files before confirming restore success -- crash causes data loss
- [ ] **Auto dream:** Has threshold checking and file locking but the consolidation body is empty -- burns threshold for no value
- [ ] **Spawn agent:** Has Pydantic schema and tool registration but returns fake results -- LLM plans multi-agent workflows that silently fail
- [ ] **WebSocket streaming:** `TokenStreamMsg` protocol type exists but `AgentLoop` uses `provider.chat()` not `provider.stream()` -- no streaming is actually sent
- [ ] **Report scheduling:** Stores entries in memory dict but no scheduler executes them -- schedules disappear on restart
- [ ] **Permission system:** Works for single-user CLI but shared across gateway sessions -- one user's `ALLOW_ALL` affects all users
- [ ] **MCP loading in gateway:** `_build()` uses `asyncio.run()` which fails under uvicorn's event loop -- MCP tools silently missing
- [ ] **VarRegistry for charts:** Chart tools store data but `list()` filters to DataFrames only -- chart variables invisible to TUI and hibernation manifest

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| GC'd fire-and-forget tasks | LOW | Add task reference set; no data structure changes needed |
| Nested `asyncio.run()` | LOW | Extract `_build()` to `builder.py`; make MCP loading awaitable |
| Cross-session permission contamination | MEDIUM | Add session-scoped permission layer; refactor `AgentLoop` permission mutation |
| Teams webhook timeout | HIGH | Requires switching from outgoing webhook to Azure Bot Service registration |
| TUI thread-safety violations | MEDIUM | Refactor callbacks to use `post_message()`; add custom message types |
| Hibernation data loss | MEDIUM | Change delete-on-load to deferred cleanup; add crash recovery |
| Feishu dedup race condition | MEDIUM | Implement two-phase dedup status (`processing` / `done`) |
| Session lock contention | LOW | Allow lock-free reads; keep lock only for agent loop execution |
| Stubs returning success | LOW | Change all stubs to return error/preview messages; update tool descriptions |
| `_build()` circular import | LOW | Extract to `builder.py`; 30-minute refactor |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Nested `asyncio.run()` in `_build()` | Phase 1 (Agent Loop) | MCP tools load successfully when gateway starts; test with `.mcp.json` present |
| `_build()` circular import / extraction | Phase 1 (Agent Loop) | `gateway/server.py` imports from `builder.py`, not `__main__.py`; gateway tests do not require `typer` |
| Stubs returning success | Phase 1 (Agent Loop) | All stub tools return clear error or are marked `(preview)` in description |
| Cross-session permission escalation | Phase 2 (Gateway) | Test: session A grants ALLOW_ALL, session B still gets prompted |
| Session lock contention | Phase 2 (Gateway) | `/api/sessions` responds < 100ms during active agent execution |
| Hibernation data loss on crash | Phase 2 (Gateway) | Kill gateway mid-restore; verify hibernation files survive; session recoverable |
| Synchronous I/O blocking event loop | Phase 2 (Gateway) | `df_transform` and hibernation wrapped in `asyncio.to_thread()`; `/health` never times out |
| TUI thread-safety | Phase 3 (TUI) | No Textual crash logs during WebSocket reconnection; all widget updates via messages |
| TUI streaming | Phase 3 (TUI) | Tokens appear incrementally in chat log; no blank screen during LLM response |
| Fire-and-forget task GC | Phase 4 (Channels) | Background tasks stored in set; Feishu messages processed reliably under GC pressure |
| Feishu dedup race condition | Phase 4 (Channels) | Gateway crash during processing; Feishu re-delivers; message processed on second attempt |
| Teams HMAC verification | Phase 4 (Channels) | Unsigned POST to `/webhook/teams` returns 401 |
| Teams async response pattern | Phase 4 (Channels) | Agent taking 15+ seconds returns result to Teams via async card update |
| Google Chat synchronous timeout | Phase 4 (Channels) | Complex queries return results asynchronously; no timeout errors |

## Sources

- [Python asyncio docs: task garbage collection warning](https://docs.python.org/3/library/asyncio-task.html) -- Official documentation on task reference retention
- [The Heisenbug lurking in your async code (Textual blog)](https://textual.textualize.io/blog/2023/02/11/the-heisenbug-lurking-in-your-async-code/) -- Textual team's writeup on the create_task GC bug
- [Textual Workers guide](https://textual.textualize.io/guide/workers/) -- Official docs on thread safety and worker patterns
- [FastAPI WebSocket patterns](https://fastapi.tiangolo.com/advanced/websockets/) -- Official WebSocket handling guidance
- [FastAPI concurrency docs](https://fastapi.tiangolo.com/async/) -- Event loop blocking and async patterns
- [Teams outgoing webhook HMAC verification](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-outgoing-webhook) -- Microsoft official docs on signature verification
- [Feishu callback handling SDK docs](https://open.feishu.cn/document/server-side-sdk/python--sdk/handle-callbacks) -- Feishu webhook patterns
- Codebase analysis: `yigthinker/gateway/server.py`, `yigthinker/channels/*/adapter.py`, `yigthinker/tui/app.py`, `yigthinker/gateway/hibernation.py`, `yigthinker/__main__.py`
- `.planning/codebase/CONCERNS.md` -- Known bugs and security issues identified in codebase audit

---
*Pitfalls research for: Multi-channel AI agent gateway with Textual TUI, session hibernation, and messaging platform webhooks*
*Researched: 2026-04-02*
