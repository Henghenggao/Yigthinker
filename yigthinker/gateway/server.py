"""GatewayServer: long-running daemon managing multi-session agent access.

Exposes:
  - WebSocket at ``/ws`` for TUI and API clients
  - HTTP API at ``/api/sessions`` for session management
  - Webhook endpoints registered by channel adapters
  - ``/health`` for liveness checks
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from yigthinker.gateway.auth import GatewayAuth
from yigthinker.visualization.exporter import ChartExporter
from yigthinker.gateway.protocol import (
    AuthResultMsg,
    ErrorMsg,
    ResponseDoneMsg,
    SessionListMsg,
    SubagentEventMsg,
    TokenStreamMsg,
    ToolCallMsg,
    ToolProgressMsg,
    ToolResultMsg,
    VarsUpdateMsg,
    parse_client_msg,
    to_json_dict,
)
from yigthinker.gateway.session_registry import ManagedSession, SessionRegistry

logger = logging.getLogger(__name__)

CHART_CACHE_DIR = Path.home() / ".yigthinker" / "chart_cache"


def _resolve_chart_path(chart_id: str, suffix: str) -> Path | None:
    """Resolve chart_id to a safe path within CHART_CACHE_DIR, or None if unsafe.

    Uses path resolution + containment check (via Path.relative_to) to reject
    traversal, absolute paths, NUL bytes, and symlinks that escape the cache.
    Legitimate ids that happen to contain ``..`` (e.g. ``chart..v2``) resolve
    within the cache dir and are accepted.
    """
    cache_root = CHART_CACHE_DIR.resolve()
    try:
        candidate = (CHART_CACHE_DIR / f"{chart_id}{suffix}").resolve()
    except (OSError, ValueError):
        return None
    try:
        candidate.relative_to(cache_root)
    except ValueError:
        return None
    return candidate


async def _safe_send(coro):
    """Wrapper for fire-and-forget sends that logs exceptions instead of swallowing them."""
    try:
        await coro
    except Exception:
        logger.debug("Failed to send tool event to WS client", exc_info=True)


class GatewayServer:
    """Central gateway daemon.

    Owns a single shared ``AgentLoop``, ``ToolRegistry``, and ``ConnectionPool``
    built via ``build_app()`` from ``yigthinker.builder``.  Sessions are managed
    by the ``SessionRegistry``.  Channel adapters register webhook routes at
    startup.
    """

    # Default origins allowed to connect via WebSocket. Prevents cross-origin
    # browser-based prompt injection. Configurable via settings.gateway.allowed_origins.
    _DEFAULT_ALLOWED_ORIGINS = frozenset({
        "http://localhost",
        "http://127.0.0.1",
    })

    def __init__(self, settings: dict[str, Any]) -> None:
        self._settings = settings
        gw_cfg = settings.get("gateway", {})
        resolved_host = gw_cfg.get("host", "127.0.0.1")
        resolved_port = int(gw_cfg.get("port", 8766))

        self._auth = GatewayAuth()
        self._settings["_gateway_token"] = self._auth.token
        self._registry = SessionRegistry(
            idle_timeout=gw_cfg.get("idle_timeout_seconds", 3600),
            max_sessions=gw_cfg.get("max_sessions", 100),
            hibernate_dir=Path(gw_cfg.get("hibernate_dir", "~/.yigthinker/hibernate")),
        )
        self._app = FastAPI(title="Yigthinker Gateway", lifespan=self._lifespan)
        self._agent_loop: Any = None
        self._pool: Any = None
        # Phase 10 / 10-01: populated by start() after build_app returns.
        # Route closures read this lazily at request time (see _mount_routes).
        self._rpa_controller: Any = None
        self._started_at = time.monotonic()
        self._ws_clients: list[_WSClient] = []
        self._eviction_task: asyncio.Task | None = None
        self._shutting_down = False
        self._adapters = self._build_adapters(settings.get("channels", {}))
        # Build allowed origins set from defaults + settings
        extra_origins = gw_cfg.get("allowed_origins", [])
        self._allowed_origins = _build_allowed_origins(
            host=resolved_host,
            port=resolved_port,
            extra_origins=extra_origins,
        )

        self._mount_routes()
        # Dashboard removed — static SPA no longer mounted

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def auth(self) -> GatewayAuth:
        return self._auth

    @property
    def registry(self) -> SessionRegistry:
        return self._registry

    async def start(self) -> None:
        """Build the agent loop and start background tasks."""
        if self._agent_loop is not None:
            return

        from yigthinker.builder import build_app

        app_ctx = await build_app(self._settings, ask_fn=None)
        self._agent_loop = app_ctx.agent_loop
        self._pool = app_ctx.pool
        # Phase 10 / 10-01: build RPAController now that build_app has
        # resolved the provider. Route closures read self._rpa_controller
        # lazily at request time.
        if (
            getattr(app_ctx, "rpa_state", None) is not None
            and getattr(app_ctx, "workflow_registry", None) is not None
        ):
            from yigthinker.gateway.rpa_controller import RPAController
            self._rpa_controller = RPAController(
                state=app_ctx.rpa_state,
                registry=app_ctx.workflow_registry,
                provider=self._agent_loop._provider,
            )
        eviction_interval = self._settings.get("gateway", {}).get("eviction_interval_seconds", 60)
        self._eviction_task = asyncio.create_task(self._eviction_loop(eviction_interval))
        for adapter in self._adapters:
            await adapter.start(self)
        logger.info("Gateway started (token=%s...)", self._auth.token[:8])

    async def stop(self) -> None:
        """Graceful shutdown: hibernate sessions, stop adapters, dispose pool."""
        self._shutting_down = True

        if self._eviction_task:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass

        # Close all WS connections
        for client in list(self._ws_clients):
            try:
                await client.ws.close(code=1001, reason="Gateway shutting down")
            except Exception:
                pass
        self._ws_clients.clear()

        for adapter in self._adapters:
            try:
                await adapter.stop()
            except Exception:
                logger.exception("Error stopping adapter %s", getattr(adapter, "name", "?"))

        await self._registry.shutdown()

        if self._pool:
            await self._pool.dispose_all()
            self._pool = None
        self._agent_loop = None

        # Phase 10 / 10-01: close the RPA state sqlite handle.
        if self._rpa_controller is not None:
            try:
                self._rpa_controller._state.close()
            except Exception:
                pass
            self._rpa_controller = None

        logger.info("Gateway stopped")

    async def handle_message(
        self,
        session_key: str,
        user_input: str,
        channel: str = "cli",
        on_tool_event: Callable[[str, dict], None] | None = None,
        quoted_messages: list | None = None,
    ) -> str | None:
        """Route a user message to the agent loop within a managed session.

        Acquires the per-session lock to prevent concurrent access. If the
        session is already running an agent loop, the message is enqueued on
        the live steering queue and None is returned (signaling the adapter
        that the input was acknowledged without a synchronous response).
        """
        # P1-2: resolve active session key (supports /new and /switch commands)
        session_key = self._registry.get_active_key(session_key)
        session = await self._registry.get_or_restore(session_key, self._settings, channel)

        # Live steering: if the agent is already running for this session, we
        # must NOT hold the session lock while the agent runs — otherwise
        # follow-up messages would block on the lock instead of being routed
        # to the steering queue. The lock is only used for the atomic
        # check-and-set of ctx._is_running.
        #
        # When steering, prepend any quoted context so the running agent sees
        # the reference alongside the follow-up input.
        def _build_steer_text() -> str:
            if not quoted_messages:
                return user_input
            refs = "\n".join(
                f'[Referenced: "{q.original_text[:200]}"]' for q in quoted_messages
            )
            return f"{refs}\n{user_input}"

        # Fast-path: observed _is_running=True without acquiring the lock.
        if session.ctx._is_running:
            session.ctx.steer(_build_steer_text())
            return None  # Signal to adapter: steering acknowledged, no response needed

        # Atomic check-and-set under lock to close the race where two callers
        # both see _is_running=False on the fast-path and then contend for
        # the lock. Whoever acquires the lock first flips _is_running=True;
        # the next acquirer re-reads it under lock, hits True, and steers.
        async with session.lock:
            if session.ctx._is_running:
                session.ctx.steer(_build_steer_text())
                return None
            session.ctx._is_running = True
            session.touch()
            session.ctx._session_registry = self._registry  # type: ignore[attr-defined]

        # Release the lock before running the agent so that concurrent
        # follow-up messages can steer via the fast-path above.
        def _on_tool_event(event_type: str, data: dict) -> None:
            """Broadcast tool events to attached WS clients (fire-and-forget)."""
            if event_type == "tool_call":
                msg = to_json_dict(ToolCallMsg(
                    tool_name=data["tool_name"],
                    tool_input=data.get("tool_input", {}),
                    tool_id=data.get("tool_id", ""),
                ))
            elif event_type == "tool_result":
                msg = to_json_dict(ToolResultMsg(
                    tool_id=data.get("tool_id", ""),
                    content=data.get("content", ""),
                    is_error=data.get("is_error", False),
                ))
            elif event_type == "subagent_event":
                msg = to_json_dict(SubagentEventMsg(
                    subagent_id=data.get("subagent_id", ""),
                    subagent_name=data.get("subagent_name", ""),
                    event=data.get("event", ""),
                    detail=data.get("detail", ""),
                ))
            elif event_type == "tool_progress":
                msg = to_json_dict(ToolProgressMsg(
                    tool=data.get("tool", ""),
                    message=data.get("message", ""),
                ))
            else:
                return
            # Fire-and-forget broadcast to all WS clients attached to this session
            for client in self._ws_clients:
                if client.session_key == session_key:
                    try:
                        asyncio.ensure_future(_safe_send(client.ws.send_json(msg)))
                    except Exception:
                        pass
            # Passthrough to external on_tool_event callback (e.g. Teams progress)
            if on_tool_event is not None:
                on_tool_event(event_type, data)

        def _on_token(text: str) -> None:
            """Broadcast token stream to all WS clients attached to this session (fire-and-forget per D-04)."""
            msg = to_json_dict(TokenStreamMsg(text=text))
            for client in self._ws_clients:
                if client.session_key == session_key:
                    try:
                        asyncio.ensure_future(_safe_send(client.ws.send_json(msg)))
                    except Exception:
                        pass

        try:
            result = await self._agent_loop.run(
                user_input, session.ctx,
                on_tool_event=_on_tool_event,
                on_token=_on_token,
            )
        finally:
            session.ctx._is_running = False
        await self._broadcast_vars_update(session)
        return result

    # ── HTTP/WS Routes ───────────────────────────────────────────────────────

    def _mount_routes(self) -> None:
        app = self._app

        @app.get("/health")
        async def health():
            return {
                "status": "ok",
                "active_sessions": self._registry.active_count,
                "uptime_seconds": round(time.monotonic() - self._started_at, 1),
            }

        @app.get("/api/sessions")
        async def list_sessions(request: Request):
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            # Filter by owner if X-Owner-Id header is provided;
            # otherwise return all (admin/CLI usage).
            owner = request.headers.get("x-owner-id", "")
            if owner:
                return self._registry.list_sessions_for_owner(owner)
            return self._registry.list_sessions()

        @app.post("/api/sessions")
        async def create_session(request: Request):
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)

            body = await request.json()
            key = body.get("key", "")
            channel = body.get("channel", "api")
            if not key:
                return JSONResponse({"error": "key required"}, status_code=400)

            session = await self._registry.get_or_restore(key, self._settings, channel)
            return session.to_info()

        @app.delete("/api/sessions/{key:path}")
        async def delete_session(key: str, request: Request):
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)

            await self._registry.hibernate(key)
            return {"ok": True, "key": key}

        # ── Phase 10 / 10-01: RPA callback + report endpoints ─────────────
        # The controller is built in start() after build_app resolves the
        # provider. Route closures read self._rpa_controller lazily so that
        # tests can inject a pre-built controller without running start().

        @app.post("/api/rpa/callback")
        async def rpa_callback(request: Request):
            if self._rpa_controller is None:
                return JSONResponse(
                    {"error": "gateway not ready"}, status_code=503,
                )
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse(
                    {"error": "unauthorized"}, status_code=401,
                )
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    {"error": "invalid JSON body"}, status_code=400,
                )
            return await self._rpa_controller.handle_callback(body)

        @app.post("/api/rpa/report")
        async def rpa_report(request: Request):
            if self._rpa_controller is None:
                return JSONResponse(
                    {"error": "gateway not ready"}, status_code=503,
                )
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse(
                    {"error": "unauthorized"}, status_code=401,
                )
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    {"error": "invalid JSON body"}, status_code=400,
                )
            return await self._rpa_controller.handle_report(body)

        # ── Chart image serving (for IM platform card embedding) ─────────────

        # Chart endpoints are unauthenticated: chart_ids are unguessable UUIDs
        # acting as capability tokens, so IM platforms (Teams/Feishu) can fetch
        # images from cards without needing to send bearer tokens.
        @app.get("/api/charts/{chart_id}.png")
        async def serve_chart_image(chart_id: str):
            """Serve rendered chart PNGs for IM platform embedding."""
            path = _resolve_chart_path(chart_id, ".png")
            if path is None:
                return JSONResponse({"error": "invalid chart id"}, status_code=400)
            if not path.exists():
                return JSONResponse({"error": "chart not found"}, status_code=404)
            return FileResponse(path, media_type="image/png")

        @app.get("/api/charts/{chart_id}")
        async def serve_chart_html(chart_id: str):
            """Serve interactive Plotly HTML for browser viewing."""
            path = _resolve_chart_path(chart_id, ".json")
            if path is None:
                return JSONResponse({"error": "invalid chart id"}, status_code=400)
            if not path.exists():
                return JSONResponse({"error": "chart not found"}, status_code=404)
            try:
                html = ChartExporter().to_html(path.read_text())
            except ValueError:
                return JSONResponse({"error": "corrupt chart data"}, status_code=500)
            return HTMLResponse(html)

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            # Validate Origin header to block cross-origin browser-based connections.
            # TUI clients (non-browser WebSocket) typically don't send Origin headers.
            origin = ws.headers.get("origin", "")
            if origin and origin.rstrip("/") not in self._allowed_origins:
                await ws.close(code=4403, reason="Cross-origin WebSocket connections not allowed")
                return

            await ws.accept()
            client = _WSClient(ws=ws)

            # First message must be auth
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
                msg = parse_client_msg(json.loads(raw))
                if msg.type != "auth" or not self._auth.verify(msg.token):
                    await ws.send_json(to_json_dict(AuthResultMsg(ok=False, message="bad token")))
                    await ws.close(code=4401, reason="Unauthorized")
                    return
                await ws.send_json(to_json_dict(AuthResultMsg(ok=True)))
            except Exception:
                await ws.close(code=4400, reason="Auth timeout or parse error")
                return

            self._ws_clients.append(client)
            try:
                await self._ws_read_loop(client)
            except WebSocketDisconnect:
                pass
            finally:
                if client in self._ws_clients:
                    self._ws_clients.remove(client)

    async def _ws_read_loop(self, client: _WSClient) -> None:
        """Process incoming WebSocket messages from an attached WebSocket client."""
        while True:
            raw = await client.ws.receive_text()
            data = json.loads(raw)
            msg = parse_client_msg(data)

            if msg.type == "attach":
                # Restore first so we can reject ownership mismatches before
                # auto-creating a fresh session. After auth, TUI or API
                # clients should be able to attach to a clean session
                # immediately, which keeps the session picker and vars panel in
                # sync on first load.
                session = self._registry.get(msg.session_key)
                if session is None:
                    session = await self._registry.restore(msg.session_key, self._settings, channel="tui")
                if session and session.ctx.owner_id and session.ctx.owner_id != msg.session_key:
                    await client.ws.send_json(to_json_dict(
                        ErrorMsg(message="Access denied: you do not own this session")
                    ))
                    continue
                if session is None:
                    session = self._registry.get_or_create(msg.session_key, self._settings, channel="tui")
                client.session_key = msg.session_key
                await client.ws.send_json(to_json_dict(
                    VarsUpdateMsg(vars=[v.__dict__ for v in session.ctx.vars.list()])
                ))
                # Gateway auth is token-based rather than user-account-based,
                # so expose the local session list for the picker UI.
                await client.ws.send_json(to_json_dict(
                    SessionListMsg(sessions=self._registry.list_sessions())
                ))

            elif msg.type == "detach":
                client.session_key = None

            elif msg.type == "user_input":
                if not client.session_key:
                    await client.ws.send_json(to_json_dict(
                        ErrorMsg(message="Not attached to a session", request_id=msg.request_id)
                    ))
                    continue

                try:
                    result = await self.handle_message(
                        client.session_key, msg.text, channel="tui"
                    )
                    await client.ws.send_json(to_json_dict(
                        ResponseDoneMsg(full_text=result, request_id=msg.request_id)
                    ))
                except Exception as exc:
                    await client.ws.send_json(to_json_dict(
                        ErrorMsg(message=str(exc), request_id=msg.request_id)
                    ))

            elif msg.type == "slash_cmd":
                # Slash commands are routed the same as user input with "/" prefix
                text = f"/{msg.command} {msg.args}".strip()
                if not client.session_key:
                    await client.ws.send_json(to_json_dict(
                        ErrorMsg(message="Not attached to a session", request_id=msg.request_id)
                    ))
                    continue
                try:
                    result = await self.handle_message(
                        client.session_key, text, channel="tui"
                    )
                    await client.ws.send_json(to_json_dict(
                        ResponseDoneMsg(full_text=result, request_id=msg.request_id)
                    ))
                except Exception as exc:
                    await client.ws.send_json(to_json_dict(
                        ErrorMsg(message=str(exc), request_id=msg.request_id)
                    ))

    async def _broadcast_vars_update(self, session: ManagedSession) -> None:
        """Send VarsUpdateMsg to all WS clients attached to this session."""
        var_infos = session.ctx.vars.list()
        msg = to_json_dict(VarsUpdateMsg(
            vars=[v.__dict__ for v in var_infos]
        ))
        dead: list[_WSClient] = []
        for client in self._ws_clients:
            if client.session_key == session.key:
                try:
                    await client.ws.send_json(msg)
                except Exception:
                    dead.append(client)
        for client in dead:
            self._ws_clients.remove(client)

    async def _eviction_loop(self, interval: int) -> None:
        """Background task: evict idle sessions periodically."""
        while True:
            await asyncio.sleep(interval)
            try:
                count = await self._registry.evict_idle()
                if count > 0:
                    logger.info("Evicted %d idle sessions", count)
            except Exception:
                logger.exception("Error during session eviction")

    def _build_adapters(self, channels: dict[str, Any]) -> list[Any]:
        adapters: list[Any] = []

        if channels.get("feishu", {}).get("enabled"):
            from yigthinker.channels.feishu.adapter import FeishuAdapter

            adapters.append(FeishuAdapter(channels["feishu"]))

        if channels.get("gchat", {}).get("enabled"):
            from yigthinker.channels.gchat.adapter import GChatAdapter

            adapters.append(GChatAdapter(channels["gchat"]))

        if channels.get("teams", {}).get("enabled"):
            from yigthinker.channels.teams.adapter import TeamsAdapter

            adapters.append(TeamsAdapter(channels["teams"]))

        return adapters

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI):
        await self.start()
        try:
            yield
        finally:
            await self.stop()


class _WSClient:
    """Tracks a connected WebSocket client and its attached session."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.session_key: str | None = None


def _extract_token(request: Request) -> str:
    """Extract bearer token from Authorization header."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


def _build_allowed_origins(
    host: str,
    port: int,
    extra_origins: list[str] | tuple[str, ...],
) -> frozenset[str]:
    origins = set(GatewayServer._DEFAULT_ALLOWED_ORIGINS)
    for local_host in {"localhost", "127.0.0.1"}:
        origins.add(f"http://{local_host}:{port}")
    if host not in {"", "0.0.0.0", "::"}:
        origins.add(f"http://{host}:{port}")
    origins.update(extra_origins)
    return frozenset(origin.rstrip("/") for origin in origins)
