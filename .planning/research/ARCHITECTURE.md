# Architecture Patterns

**Domain:** Multi-channel AI agent gateway with TUI client for financial data analysis
**Researched:** 2026-04-02

## Recommended Architecture

The existing scaffolded architecture is fundamentally sound. It follows the **Unified Agent Gateway** pattern: a single stateless AgentLoop serves all channels through a centralized gateway daemon that owns session lifecycle. This is the correct pattern for this domain.

The architecture has three tiers:

```
Tier 1: Input Surfaces          Tier 2: Gateway Daemon           Tier 3: Agent Core
+------------------+            +----------------------+         +------------------+
| CLI REPL         |--direct--->|                      |         |                  |
+------------------+            |  GatewayServer       |         |  AgentLoop       |
                                |    SessionRegistry   |-------->|    ToolRegistry   |
+------------------+  WebSocket |    _ws_clients[]     |         |    HookExecutor  |
| TUI (Textual)    |---------->|    Channel Adapters   |         |    Permissions   |
+------------------+            |    Auth              |         |                  |
                                |                      |         +--------+---------+
+------------------+  Webhook   |  /webhook/feishu     |                  |
| Feishu           |---------->|  /webhook/teams      |         +--------v---------+
| Teams            |---------->|  /webhook/gchat      |         | LLMProvider      |
| Google Chat      |---------->|                      |         | (Claude/OpenAI/  |
+------------------+            +----------------------+         |  Ollama/Azure)   |
                                         |                      +------------------+
                                +--------v---------+
                                | SessionContext    |
                                |   .vars (VarReg) |
                                |   .messages      |
                                |   .stats         |
                                +------------------+
```

**Critical observation:** The CLI REPL bypasses the Gateway entirely and calls AgentLoop directly. This is correct for development and local use but means the CLI path has no session registry, no hibernation, and no WebSocket broadcast. The two paths (CLI-direct and Gateway-mediated) must be kept coherent.

### Component Boundaries

| Component | Responsibility | Communicates With | Current State |
|-----------|---------------|-------------------|---------------|
| **AgentLoop** (`agent.py`) | LLM-tool cycle: chat, parse, hook, execute, loop | LLMProvider, ToolRegistry, HookExecutor, PermissionSystem, SessionContext | Real implementation, functional |
| **GatewayServer** (`gateway/server.py`) | FastAPI daemon: WebSocket, HTTP API, webhook routes, session lifecycle | SessionRegistry, AgentLoop, ChannelAdapters, _WSClient list | Real implementation, needs testing |
| **SessionRegistry** (`gateway/session_registry.py`) | Session CRUD, idle eviction, hibernate/restore dispatch | ManagedSession, SessionHibernator | Real implementation |
| **SessionHibernator** (`gateway/hibernation.py`) | Serialize/deserialize sessions to disk (Parquet + JSONL) | ManagedSession, SessionContext, VarRegistry | Real implementation |
| **GatewayWSClient** (`tui/ws_client.py`) | WebSocket client with auth and exponential backoff reconnection | GatewayServer /ws endpoint | Real implementation, needs stabilization |
| **YigthinkerTUI** (`tui/app.py`) | Textual app: compose widgets, route messages, manage state | GatewayWSClient, ChatLog, VarsPanel, StatusBar | Scaffolded, widget stubs |
| **ChannelAdapter** (`channels/base.py`) | Protocol for messaging platform integrations | GatewayServer.handle_message(), platform APIs | Protocol defined, Feishu implemented |
| **FeishuAdapter** (`channels/feishu/adapter.py`) | Feishu webhook, 3s ACK, card update, event dedup | GatewayServer, lark-oapi SDK, EventDeduplicator | Real implementation, needs testing |
| **WebSocket Protocol** (`gateway/protocol.py`) | Typed message dataclasses for Gateway-TUI communication | GatewayServer, GatewayWSClient | Fully defined, 13 message types |

### Data Flow

**Flow 1: TUI user sends a message**

```
1. User types in InputBar
2. YigthinkerTUI.on_input_submitted() -> ws_client.send_input(text)
3. GatewayWSClient sends UserInputMsg{text, request_id} over WebSocket
4. GatewayServer._ws_read_loop() parses message
5. GatewayServer.handle_message(session_key, text, "tui")
6.   SessionRegistry.get_or_restore(key) -> ManagedSession
7.   async with session.lock: AgentLoop.run(text, session.ctx)
8.   AgentLoop enters LLM-tool cycle (may run N tool calls)
9.   Final text returned
10.  _broadcast_vars_update(session) -> VarsUpdateMsg to all attached WS clients
11.  ResponseDoneMsg{full_text, request_id} sent to requesting WS client
12. TUI _on_ws_message dispatches to ChatLog.append_response()
```

**Flow 2: Feishu user sends a message**

```
1. Feishu platform POSTs to /webhook/feishu
2. FeishuAdapter validates token, checks dedup
3. Returns {"code": 0} immediately (3-second ACK)
4. asyncio.create_task(_process_event(body))
5.   Sends "thinking..." card to user
6.   gateway.handle_message(session_key, text, "feishu")
7.   AgentLoop runs (same as above)
8.   PATCHes thinking card with result card
```

**Flow 3: Session hibernation**

```
1. Eviction loop detects idle session (> idle_timeout, unlocked)
2. SessionRegistry.hibernate(key)
3. SessionHibernator.save(session)
4.   metadata.json: session ID, key, channel, timestamps
5.   messages.jsonl: conversation history
6.   stats.json: usage counters
7.   vars/*.parquet: DataFrames (with pickle fallback)
8.   vars/*.json: string vars (chart configs)
9. Session removed from in-memory dict
```

## Patterns to Follow

### Pattern 1: Per-Session Lock for Concurrency

**What:** Every ManagedSession has an `asyncio.Lock`. All message processing acquires this lock before calling AgentLoop.run().

**When:** Always. The AgentLoop is stateless but SessionContext is mutable. Without the lock, two concurrent messages to the same session would corrupt message history.

**Why this is correct:** The current implementation uses `async with session.lock` in `handle_message()`. This serializes requests per-session while allowing different sessions to process concurrently. This is the standard pattern for async session state management.

**Pitfall to watch:** The lock is held for the entire AgentLoop.run() duration (which includes LLM API calls that can take 10-60 seconds). This means a second message to the same session queues behind the first. This is the correct behavior (you cannot interleave two agent runs on the same context), but the TUI should show "processing..." state so the user understands why their second message is waiting.

```python
# Current implementation (correct)
async with session.lock:
    session.touch()
    result = await self._agent_loop.run(user_input, session.ctx)
```

### Pattern 2: Discriminated Union Message Protocol

**What:** All WebSocket messages have a `type` field as discriminator. Client messages and server messages are separate namespaces. Parsed via `parse_client_msg()` lookup table.

**When:** All Gateway-TUI communication.

**Why this is correct:** The protocol.py module defines 13 message types (5 client-to-server, 8 server-to-client) as dataclasses. This is clean and extensible. Adding a new message type requires: (1) add a dataclass, (2) add to the lookup dict if client-originated.

**Enhancement needed:** The protocol currently lacks `token` (streaming) messages being sent during processing. The `TokenStreamMsg` dataclass exists but is never emitted by the server. This is the single most impactful gap -- without it, the TUI shows nothing until the full response is ready.

### Pattern 3: Exponential Backoff Reconnection with Auth Gate

**What:** The TUI WebSocket client (`GatewayWSClient.connect_loop()`) reconnects with exponential backoff (1s, 2s, 4s, ... 30s cap). Auth failure is terminal (no reconnect).

**When:** TUI loses connection to gateway.

**Why this is correct:** The implementation correctly distinguishes between transient failures (network blip -- retry) and permanent failures (bad token -- stop). The 30-second cap prevents excessive wait times.

**Enhancement needed:** Add jitter to backoff (`delay * (0.5 + random() * 0.5)`) to prevent thundering herd when gateway restarts with multiple TUI clients. Also add session reattachment after reconnect -- currently the client reconnects and re-authenticates but does not re-send the `AttachMsg` for the previously active session.

### Pattern 4: 3-Second ACK with Background Processing

**What:** Channel adapters (Feishu) return HTTP response immediately and process the message in a background asyncio task.

**When:** All webhook-based channel adapters where the platform has a response timeout.

**Why this is correct:** Feishu requires webhook response within 3 seconds. The adapter returns `{"code": 0}` immediately, then processes asynchronously. The "thinking..." card + PATCH pattern gives the user feedback during processing.

**Critical requirement:** The `asyncio.create_task()` call means the task is fire-and-forget. If the gateway shuts down during processing, the task is cancelled. The adapter should handle `asyncio.CancelledError` gracefully.

### Pattern 5: Textual Worker for WebSocket Connection

**What:** The TUI runs the WebSocket connection loop as a Textual `Worker` via `self.run_worker(self._ws_client.connect_loop(), exclusive=True)`.

**When:** TUI startup.

**Why this is correct:** Textual workers run coroutines without blocking the main event loop. The `exclusive=True` flag ensures only one connection loop runs at a time, preventing duplicate connections.

**Enhancement needed:** The `_on_ws_message` callback is called synchronously from the worker thread. If it triggers Textual widget updates (which it does -- `ChatLog.append_response()`, etc.), these calls must be thread-safe. Textual's `call_from_thread()` or `App.post_message()` should be used instead of direct widget method calls from the worker callback context.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking the Gateway Event Loop

**What:** Running CPU-intensive operations (DataFrame transforms, Parquet serialization) directly in the async event loop without `asyncio.to_thread()`.

**Why bad:** Blocks all concurrent WebSocket connections and HTTP requests. A single heavy DataFrame operation could freeze the entire gateway for seconds.

**Instead:** Wrap CPU-bound operations in `asyncio.to_thread()`. The Feishu adapter already does this for `lark-oapi` calls (`await asyncio.to_thread(self._client.im.v1.message.create, request)`). Apply the same pattern to hibernation serialization and tool execution where DataFrames are large.

### Anti-Pattern 2: Message Accumulation Without Backpressure

**What:** Sending VarsUpdateMsg and ResponseDoneMsg to all attached WebSocket clients without checking if the client can keep up.

**Why bad:** A slow TUI client accumulates messages in the send buffer, consuming memory. Eventually the WebSocket write buffer overflows.

**Instead:** Use asyncio.Queue with a bounded size per client. If the queue is full, disconnect the slow client rather than blocking the broadcast. The current code already handles dead clients (catches exceptions and removes them), but does not prevent buffer accumulation.

### Anti-Pattern 3: Dual-Path Divergence (CLI vs Gateway)

**What:** The CLI REPL calls AgentLoop directly while the Gateway calls it through SessionRegistry. Features added to the Gateway path (session hibernation, vars broadcast, concurrent session management) do not exist in the CLI path.

**Why bad:** Two code paths that should behave identically diverge over time. Users switching between CLI and TUI get different behavior.

**Instead:** Accept this as intentional. The CLI is the lightweight development path; the Gateway is the production path. But ensure the CLI path uses the same SessionContext construction and can optionally connect to a running Gateway (this is what `yigthinker tui` already does). Do not try to make the CLI itself run through the Gateway.

### Anti-Pattern 4: Pickle for Session Hibernation

**What:** The hibernation system falls back to Python pickle for non-DataFrame, non-string variables.

**Why bad:** Pickle is a security risk (arbitrary code execution on deserialization) and is not portable across Python versions. If a chart JSON object is stored as a dict instead of a string, it gets pickled.

**Instead:** Serialize all variables through JSON-safe formats. DataFrames go to Parquet. Strings go to JSON text files. Dicts/lists go to JSON files. Only use pickle as a last resort and log a prominent warning. The current code logs a warning but the fallback is too easy to hit.

## Scalability Considerations

| Concern | 1-5 users (dev) | 10-50 users (team) | 100+ users (org) |
|---------|-----------------|---------------------|-------------------|
| **Concurrent sessions** | In-memory dict, no eviction needed | Idle eviction at 1hr, 100 max sessions | Need external session store (Redis), horizontal scaling |
| **LLM API concurrency** | Sequential OK | Per-session lock serializes correctly | Need request queuing/rate limiting per provider |
| **WebSocket connections** | Direct dict iteration for broadcast | Fine up to ~50 clients | Need connection groups, pub/sub (Redis pub/sub) |
| **DataFrame memory** | Unlimited, user manages | Eviction by idle timeout + parquet hibernate | Memory budget per session, aggressive eviction |
| **Hibernation I/O** | Local filesystem | Local filesystem, SSD recommended | Shared storage (S3/NFS) or database-backed |

For the current milestone (stabilization), the 1-5 user tier is the target. The architecture does not need horizontal scaling yet, but the design decisions being made now should not preclude it.

## Build Order (Dependencies)

The bottom-up dependency chain dictates build order:

```
Phase 1: Agent Loop + Providers (no external dependencies)
    |
    v
Phase 2: Gateway Server + Session Registry (depends on working AgentLoop)
    |
    v
Phase 3: TUI Client (depends on working Gateway WebSocket endpoint)
    |
    +---> Phase 4a: Streaming Protocol (enhances TUI, needs Gateway changes)
    |
    +---> Phase 4b: Channel Adapters (depends on working Gateway.handle_message)
    |
    v
Phase 5: Session Memory + Auto Dream (enhances Agent Loop, can test via CLI)
```

**Why this order:**
1. **Agent Loop first** because everything calls `AgentLoop.run()`. If this is broken, nothing else can be tested.
2. **Gateway second** because it is the hub that TUI and channels connect to. Testing Gateway requires a working AgentLoop.
3. **TUI third** because it is the primary user-facing surface for development. Testing TUI requires a running Gateway.
4. **Streaming and Channels in parallel** because they are independent features that both depend on the Gateway but not on each other.
5. **Memory features last** because they are enhancement layers on top of a working system.

**The critical integration boundary** is between the Gateway and the AgentLoop. The Gateway currently calls `await self._agent_loop.run(user_input, session.ctx)` and blocks until completion. For streaming support, this needs to become an async generator or callback-based pattern where the AgentLoop yields intermediate events (tokens, tool calls, tool results) that the Gateway can forward over WebSocket in real time.

## Key Architecture Decisions Still Needed

### Decision 1: Streaming Integration

The AgentLoop currently returns `str` from `run()`. For token streaming, it needs to yield intermediate events. Two approaches:

**Option A: Async generator.** `async for event in agent_loop.stream(input, ctx)` where events are `TokenEvent`, `ToolCallEvent`, `ToolResultEvent`, `DoneEvent`. The Gateway wraps each event as a protocol message and sends to WebSocket. **Recommended** because it is the standard pattern in the Python AI ecosystem (LangChain, AutoGen, Pydantic AI all use async iterators for streaming).

**Option B: Callback injection.** Pass an `on_event` callback to `run()`. The callback is called for each intermediate event. The Gateway provides a callback that sends WebSocket messages. Simpler to retrofit but harder to compose.

### Decision 2: TUI Thread Safety

The TUI's `_on_ws_message` callback is invoked from the WebSocket worker context but directly calls widget methods (`ChatLog.append_response()`). Textual requires UI mutations to happen on the main thread. Options:

**Use `App.call_from_thread()`** to dispatch widget updates to the main thread. This is the official Textual pattern for worker-to-UI communication.

### Decision 3: Request-Response Correlation

The protocol includes `request_id` on `UserInputMsg` and `ResponseDoneMsg` but not on intermediate streaming messages. For the TUI to correctly associate streaming tokens with a specific request (when a user might send multiple messages in quick succession), intermediate messages need either a `request_id` or a `session_key + sequence_number` correlation mechanism.

**Recommendation:** Add `request_id` to `TokenStreamMsg`, `ToolCallMsg`, and `ToolResultMsg`. The per-session lock already prevents true concurrency, but the TUI client needs the correlation to handle out-of-order delivery after reconnection.

## Sources

- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [Textual Workers Guide](https://textual.textualize.io/guide/workers/)
- [Textual App Basics](https://textual.textualize.io/guide/app/)
- [WebSocket Design Patterns (websockets library)](https://websockets.readthedocs.io/en/stable/howto/patterns.html)
- [Integrating AutoGen Agents with FastAPI + WebSockets + Queues](https://newsletter.victordibia.com/p/integrating-autogen-agents-into-your) -- queue-based message bus pattern
- [WebSocket Reconnection with Exponential Backoff](https://oneuptime.com/blog/post/2026-01-27-websocket-reconnection/view)
- [WebSocket Heartbeat/Ping-Pong](https://oneuptime.com/blog/post/2026-01-27-websocket-heartbeat/view)
- [Multi-Channel AI Agent Deployment Patterns](https://www.mindstudio.ai/blog/multi-channel-ai-agent-deployment-slack-teams)
- [AI Agent Orchestration Patterns - Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- [MCP Gateways: AI Agent Architecture 2026](https://composio.dev/content/mcp-gateways-guide)
- [Streaming AI Agent with FastAPI & LangGraph 2025-26](https://dev.to/kasi_viswanath/streaming-ai-agent-with-fastapi-langgraph-2025-26-guide-1nkn)
- [Feishu Open Platform - Handle Callbacks](https://open.feishu.cn/document/server-side-sdk/python--sdk/handle-callbacks)
- Codebase analysis: `yigthinker/gateway/server.py`, `tui/app.py`, `tui/ws_client.py`, `gateway/protocol.py`, `agent.py`, `session.py`, `channels/feishu/adapter.py`
