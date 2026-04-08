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
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from yigthinker.gateway.auth import GatewayAuth
from yigthinker.gateway.protocol import (
    AuthResultMsg,
    ErrorMsg,
    ResponseDoneMsg,
    SessionListMsg,
    SubagentEventMsg,
    TokenStreamMsg,
    ToolCallMsg,
    ToolResultMsg,
    VarsUpdateMsg,
    parse_client_msg,
    to_json_dict,
)
from yigthinker.gateway.session_registry import ManagedSession, SessionRegistry

logger = logging.getLogger(__name__)


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
        self._started_at = time.monotonic()
        self._ws_clients: list[_WSClient] = []
        self._eviction_task: asyncio.Task | None = None
        self._shutting_down = False
        self._adapters = self._build_adapters(settings.get("channels", {}))
        self._dashboard_entries: list[dict[str, Any]] = []  # kept for API compat

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

        logger.info("Gateway stopped")

    async def handle_message(
        self,
        session_key: str,
        user_input: str,
        channel: str = "cli",
    ) -> str:
        """Route a user message to the agent loop within a managed session.

        Acquires the per-session lock to prevent concurrent access.
        """
        session = await self._registry.get_or_restore(session_key, self._settings, channel)

        async with session.lock:
            session.touch()

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
                else:
                    return
                # Fire-and-forget broadcast to all WS clients attached to this session
                for client in self._ws_clients:
                    if client.session_key == session_key:
                        try:
                            asyncio.ensure_future(_safe_send(client.ws.send_json(msg)))
                        except Exception:
                            pass

            def _on_token(text: str) -> None:
                """Broadcast token stream to all WS clients attached to this session (fire-and-forget per D-04)."""
                msg = to_json_dict(TokenStreamMsg(text=text))
                for client in self._ws_clients:
                    if client.session_key == session_key:
                        try:
                            asyncio.ensure_future(_safe_send(client.ws.send_json(msg)))
                        except Exception:
                            pass

            result = await self._agent_loop.run(
                user_input, session.ctx,
                on_tool_event=_on_tool_event,
                on_token=_on_token,
            )
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

        @app.get("/api/dashboard/entries")
        async def list_dashboard_entries(request: Request):
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return list(self._dashboard_entries)

        @app.post("/api/dashboard/push")
        async def push_dashboard_entry(request: Request):
            token = _extract_token(request)
            if not self._auth.verify(token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)

            body = await request.json()
            entry = {
                "dashboard_id": str(body.get("dashboard_id", "")).strip(),
                "title": str(body.get("title", "")).strip(),
                "chart_json": str(body.get("chart_json", "")).strip(),
                "description": str(body.get("description", "")).strip(),
            }
            if not entry["dashboard_id"] or not entry["title"] or not entry["chart_json"]:
                return JSONResponse({"error": "dashboard_id, title, and chart_json are required"}, status_code=400)

            self._dashboard_entries.append(entry)
            await self._broadcast_dashboard_entry(entry)
            return {"ok": True, "dashboard_id": entry["dashboard_id"]}

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
        """Process incoming WebSocket messages from a TUI or dashboard client."""
        while True:
            raw = await client.ws.receive_text()
            data = json.loads(raw)
            msg = parse_client_msg(data)

            if msg.type == "attach":
                # Restore first so we can reject ownership mismatches before
                # auto-creating a fresh session. After auth, dashboard and TUI
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

    async def _broadcast_dashboard_entry(self, entry: dict[str, Any]) -> None:
        dead: list[_WSClient] = []
        message = {"type": "dashboard_entry", "entry": entry}
        for client in self._ws_clients:
            try:
                await client.ws.send_json(message)
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
