import pandas as pd
import pytest
from fastapi.testclient import TestClient

from yigthinker.gateway.server import GatewayServer


class DummyAuth:
    def __init__(self) -> None:
        self.token = "test-token"

    def verify(self, candidate: str) -> bool:
        return candidate == self.token


class FakeAgentLoop:
    async def run(self, user_input: str, ctx, **kwargs) -> str:
        ctx.vars.set("revenue", pd.DataFrame({"value": [1, 2, 3]}))
        ctx.messages.append(type("Msg", (), {"role": "assistant", "content": user_input})())
        return f"echo:{user_input}"


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr("yigthinker.gateway.server.GatewayAuth", DummyAuth)
    settings = {
        "gateway": {
            "idle_timeout_seconds": 3600,
            "max_sessions": 10,
            "hibernate_dir": str(tmp_path / "hibernate"),
            "eviction_interval_seconds": 60,
        },
        "channels": {},
    }
    gateway = GatewayServer(settings)

    async def fake_start() -> None:
        gateway._agent_loop = FakeAgentLoop()
        gateway._pool = None

    async def fake_stop() -> None:
        return None

    gateway.start = fake_start
    gateway.stop = fake_stop
    return gateway


def _receive_attach_messages(ws):
    msg_a = ws.receive_json()
    msg_b = ws.receive_json()
    types = {msg_a["type"], msg_b["type"]}
    assert types == {"vars_update", "session_list"}
    vars_msg = msg_a if msg_a["type"] == "vars_update" else msg_b
    session_list_msg = msg_a if msg_a["type"] == "session_list" else msg_b
    return vars_msg, session_list_msg


def test_session_api_requires_auth(server):
    with TestClient(server.app) as client:
        response = client.get("/api/sessions")
    assert response.status_code == 401


def test_health_endpoint(server):
    """GW-01: /health returns status ok with session count and uptime."""
    with TestClient(server.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "active_sessions" in body
    assert "uptime_seconds" in body
    assert isinstance(body["active_sessions"], int)
    assert isinstance(body["uptime_seconds"], (int, float))


def test_create_session_via_api(server):
    with TestClient(server.app) as client:
        response = client.post(
            "/api/sessions",
            json={"key": "tui:user1", "channel": "tui"},
            headers={"Authorization": f"Bearer {server.auth.token}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "tui:user1"
    assert body["channel_origin"] == "tui"


def test_removed_dashboard_routes_return_404(server):
    with TestClient(server.app) as client:
        response = client.get(
            "/api/dashboard/entries",
            headers={"Authorization": f"Bearer {server.auth.token}"},
        )
        post_response = client.post(
            "/api/dashboard/push",
            json={"title": "x"},
            headers={"Authorization": f"Bearer {server.auth.token}"},
        )
    assert response.status_code == 404
    assert post_response.status_code == 404


def test_websocket_round_trip_and_vars_update(server):
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": server.auth.token})
            assert ws.receive_json()["ok"] is True

            ws.send_json({"type": "attach", "session_key": "tui:user1"})
            attach_vars, session_list = _receive_attach_messages(ws)
            assert attach_vars["vars"] == []
            assert session_list["sessions"][0]["key"] == "tui:user1"

            ws.send_json({"type": "user_input", "text": "hello", "request_id": "r1"})
            first = ws.receive_json()
            second = ws.receive_json()

    assert {first["type"], second["type"]} == {"vars_update", "response_done"}
    response = first if first["type"] == "response_done" else second
    vars_update = first if first["type"] == "vars_update" else second
    assert response["full_text"] == "echo:hello"
    assert vars_update["vars"][0]["name"] == "revenue"


@pytest.mark.asyncio
async def test_handle_message_restores_hibernated_session(server):
    session = server.registry.get_or_create("tui:user1", {}, "tui")
    session.ctx.vars.set("restored_df", pd.DataFrame({"x": [1]}))
    await server.registry.hibernate("tui:user1")

    class RestoringAgent:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            assert "restored_df" in ctx.vars
            return f"restored:{user_input}"

    server._agent_loop = RestoringAgent()
    result = await server.handle_message("tui:user1", "resume", channel="tui")
    assert result == "restored:resume"


@pytest.mark.asyncio
async def test_concurrent_messages_steer_when_running(server):
    """GW-04 / Task 10 (Live Steering): With live steering, concurrent messages
    to a running session are routed to the steering queue rather than serialized
    behind the session lock. The first caller runs the agent; the second is
    enqueued and returns None immediately.
    """
    import asyncio

    call_order: list[str] = []

    class SlowAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            call_order.append(f"start:{user_input}")
            await asyncio.sleep(0.05)
            call_order.append(f"end:{user_input}")
            return f"echo:{user_input}"

    server._agent_loop = SlowAgentLoop()

    # Fire two concurrent messages to the SAME session key
    task1 = asyncio.create_task(server.handle_message("test:serial", "msg1", channel="test"))
    # Small delay so task1 has a chance to flip _is_running = True first
    await asyncio.sleep(0.005)
    task2 = asyncio.create_task(server.handle_message("test:serial", "msg2", channel="test"))
    results = await asyncio.gather(task1, task2)

    # One call runs to completion, the other is steered (returns None)
    assert set(results) == {"echo:msg1", None}

    # Only one agent invocation occurred
    assert len([e for e in call_order if e.startswith("start:")]) == 1
    assert len([e for e in call_order if e.startswith("end:")]) == 1

    # The steered message was enqueued for consumption by the agent
    session = server.registry.get("test:serial")
    assert session is not None
    assert session.ctx.drain_steerings() == ["msg2"]


def test_websocket_e2e_full_flow(server):
    """D-05 / GW-02: Full WebSocket flow - auth, attach, input, response, vars."""
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as ws:
            # Step 1: Authenticate
            ws.send_json({"type": "auth", "token": server.auth.token})
            auth_result = ws.receive_json()
            assert auth_result["type"] == "auth_result"
            assert auth_result["ok"] is True

            # Step 2: Attach to session
            ws.send_json({"type": "attach", "session_key": "tui:e2e-test"})
            attach_vars_msg, session_list_msg = _receive_attach_messages(ws)
            assert attach_vars_msg["vars"] == []
            assert isinstance(session_list_msg["sessions"], list)
            assert session_list_msg["sessions"][0]["key"] == "tui:e2e-test"

            # Step 3: Send user input
            ws.send_json({"type": "user_input", "text": "analyze revenue", "request_id": "req-001"})

            # Step 4: Receive response_done and vars_update (order may vary)
            msg_a = ws.receive_json()
            msg_b = ws.receive_json()
            types = {msg_a["type"], msg_b["type"]}
            assert types == {"response_done", "vars_update"}

            response_msg = msg_a if msg_a["type"] == "response_done" else msg_b
            vars_msg = msg_a if msg_a["type"] == "vars_update" else msg_b

            # Step 5: Verify response content
            assert response_msg["full_text"] == "echo:analyze revenue"
            assert response_msg["request_id"] == "req-001"

            # Step 6: Verify vars update includes var_type
            assert len(vars_msg["vars"]) >= 1
            revenue_var = vars_msg["vars"][0]
            assert revenue_var["name"] == "revenue"
            assert "shape" in revenue_var
            assert "dtypes" in revenue_var
            assert "var_type" in revenue_var  # Verifies Plan 01's VarsUpdate fix


def test_websocket_attach_lists_existing_sessions_for_picker(server):
    server.registry.get_or_create("tui:first", {}, "tui")
    server.registry.get_or_create("tui:second", {}, "tui")

    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": server.auth.token})
            assert ws.receive_json()["ok"] is True

            ws.send_json({"type": "attach", "session_key": "tui:first"})
            _attach_vars, session_list = _receive_attach_messages(ws)

    assert {session["key"] for session in session_list["sessions"]} == {"tui:first", "tui:second"}


def test_websocket_bad_auth_rejected(server):
    """GW-02: WebSocket rejects invalid token."""
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "wrong-token"})
            auth_result = ws.receive_json()
            assert auth_result["type"] == "auth_result"
            assert auth_result["ok"] is False


@pytest.mark.asyncio
async def test_streaming_broadcast_sends_token_msgs(server):
    """STRM-03: Gateway broadcasts TokenStreamMsg to attached WS clients during streaming."""
    from unittest.mock import AsyncMock, MagicMock

    sent_messages: list[dict] = []

    class StreamingAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs):
            on_token = kwargs.get("on_token")
            assert on_token is not None, "on_token callback must be passed to AgentLoop.run()"
            on_token("Hello")
            on_token(" world")
            return "Hello world"

    server._agent_loop = StreamingAgentLoop()

    # Create a mock WS client attached to our session
    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock(side_effect=lambda msg: sent_messages.append(msg))

    from yigthinker.gateway.server import _WSClient
    client = _WSClient(ws=mock_ws)
    client.session_key = "tui:stream-test"
    server._ws_clients.append(client)

    result = await server.handle_message("tui:stream-test", "hello", channel="tui")
    assert result == "Hello world"

    # Allow fire-and-forget tasks to complete
    import asyncio
    await asyncio.sleep(0.1)

    # Filter for token messages only (vars_update also sent)
    token_msgs = [m for m in sent_messages if m.get("type") == "token"]
    assert len(token_msgs) == 2
    assert token_msgs[0]["text"] == "Hello"
    assert token_msgs[1]["text"] == " world"


@pytest.mark.asyncio
async def test_handle_message_race_atomic_check_and_set(server):
    """Task 10 (Live Steering) — regression: two callers that both observe
    _is_running=False on the pre-lock fast-path MUST NOT both run the agent.

    The bug: if check-and-set of _is_running is not atomic under the session
    lock, two concurrent callers both fall through to the lock, task1 flips
    _is_running=True and runs the agent, task1 finishes and resets
    _is_running=False, task2 acquires the lock and ALSO runs the agent as
    a full turn instead of being treated as steering.

    The fix: re-check _is_running under the lock. The second acquirer
    observes True and steers.

    To make the race deterministic we replace session.lock with a lock
    that blocks both acquirers at a known point, then releases them in
    order so both observe _is_running=False at the pre-lock fast-path
    and then contend for the lock.
    """
    import asyncio

    call_order: list[str] = []

    class SlowAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            call_order.append(f"start:{user_input}")
            await asyncio.sleep(0.05)
            call_order.append(f"end:{user_input}")
            return f"echo:{user_input}"

    server._agent_loop = SlowAgentLoop()

    # Pre-create the session so we can install a gated lock. A gated lock
    # lets us force both callers to reach the lock-acquire point while
    # _is_running is still False, then releases them in order. This exposes
    # the race without relying on asyncio scheduling luck.
    session = server.registry.get_or_create("test:race", {}, "test")

    class _GatedLock:
        def __init__(self) -> None:
            self._inner = asyncio.Lock()
            self._gate = asyncio.Event()
            self._arrivals = 0
            self._required = 2

        async def __aenter__(self):
            # Wait until both contenders have arrived at the lock. This
            # guarantees both saw _is_running=False on the pre-lock
            # fast-path before either proceeds past acquire.
            self._arrivals += 1
            if self._arrivals >= self._required:
                self._gate.set()
            await self._gate.wait()
            await self._inner.acquire()
            return self

        async def __aexit__(self, *exc):
            self._inner.release()

    session.lock = _GatedLock()  # type: ignore[assignment]

    task1 = asyncio.create_task(server.handle_message("test:race", "msg1", channel="test"))
    task2 = asyncio.create_task(server.handle_message("test:race", "msg2", channel="test"))
    results = await asyncio.gather(task1, task2)

    # Exactly one agent run; the other must have been steered (None).
    agent_runs = [e for e in call_order if e.startswith("start:")]
    assert len(agent_runs) == 1, (
        f"Expected exactly 1 agent run after race; got {len(agent_runs)}: {call_order}"
    )
    assert results.count(None) == 1, (
        f"Expected exactly one steering (None) result; got results={results}"
    )
    # The non-None result corresponds to the winning agent run.
    winner = next(r for r in results if r is not None)
    assert winner in {"echo:msg1", "echo:msg2"}

    # The losing message was enqueued for steering.
    drained = session.ctx.drain_steerings()
    assert len(drained) == 1
    assert drained[0] in {"msg1", "msg2"}


@pytest.mark.asyncio
async def test_handle_message_steers_when_already_running(server):
    """Task 10 (Live Steering): when _is_running is True on arrival,
    handle_message enqueues the input onto the steering queue and returns
    None WITHOUT invoking _agent_loop.run().
    """
    call_count = {"n": 0}

    class RecordingAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            call_count["n"] += 1
            return f"ran:{user_input}"

    server._agent_loop = RecordingAgentLoop()

    # Pre-create the session and mark it as running
    session = server.registry.get_or_create("tui:steer-test", {}, "tui")
    session.ctx._is_running = True

    result = await server.handle_message(
        "tui:steer-test", "steer me", channel="tui"
    )

    assert result is None, "steering path must return None"
    assert call_count["n"] == 0, "agent_loop.run must not be invoked during steering"

    drained = session.ctx.drain_steerings()
    assert drained == ["steer me"], "input must be enqueued on the steering queue"


async def test_handle_message_prepends_quoted_context_to_steering(server):
    """Task 15: quoted_messages kwarg prepends [Referenced: ...] lines to the
    text enqueued on the steering queue.
    """
    from yigthinker.session import QuotedMessage

    class NoopAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            return "never-called"

    server._agent_loop = NoopAgentLoop()
    session = server.registry.get_or_create("tui:steer-ref", {}, "tui")
    session.ctx._is_running = True

    quotes = [
        QuotedMessage(original_id="m1", original_text="what were Q3 sales?"),
        QuotedMessage(original_id="m2", original_text="a" * 300),  # truncated to 200
    ]
    result = await server.handle_message(
        "tui:steer-ref", "compare to Q4", channel="tui", quoted_messages=quotes
    )

    assert result is None
    drained = session.ctx.drain_steerings()
    assert len(drained) == 1
    text = drained[0]
    assert '[Referenced: "what were Q3 sales?"]' in text
    assert f'[Referenced: "{"a" * 200}"]' in text
    assert '[Referenced: "' + "a" * 201 + '"]' not in text  # truncation at 200
    assert text.endswith("compare to Q4")


async def test_handle_message_no_quotes_passes_plain_text(server):
    """Task 15: steering without quoted_messages enqueues plain user_input."""
    class NoopAgentLoop:
        async def run(self, user_input: str, ctx, **kwargs) -> str:
            return "never-called"

    server._agent_loop = NoopAgentLoop()
    session = server.registry.get_or_create("tui:steer-plain", {}, "tui")
    session.ctx._is_running = True

    result = await server.handle_message(
        "tui:steer-plain", "just steer", channel="tui"
    )
    assert result is None
    assert session.ctx.drain_steerings() == ["just steer"]
