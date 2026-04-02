from __future__ import annotations

import json
import secrets
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

DrilldownHandler = Callable[[str], Awaitable[str]]

# Origins allowed to connect to the WebSocket. Localhost origins only —
# prevents cross-origin browser-based prompt injection attacks.
_ALLOWED_ORIGINS = frozenset({
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
})


class DashboardEntry(BaseModel):
    dashboard_id: str
    title: str
    chart_json: str
    description: str = ""


class SessionNotFoundError(KeyError):
    """Raised when a dashboard drilldown references an unknown active session."""


class DashboardSessionBridge:
    """Routes dashboard drilldown messages back into active sessions."""

    def __init__(self) -> None:
        self._handlers: dict[str, DrilldownHandler] = {}
        self._tokens: dict[str, str] = {}

    def register_session(self, session_id: str, handler: DrilldownHandler) -> str:
        """Register a session handler and return the auth token for drilldowns."""
        self._handlers[session_id] = handler
        token = secrets.token_hex(32)
        self._tokens[session_id] = token
        return token

    def unregister_session(self, session_id: str) -> None:
        self._handlers.pop(session_id, None)
        self._tokens.pop(session_id, None)

    def verify_token(self, session_id: str, token: str) -> bool:
        expected = self._tokens.get(session_id)
        if not expected:
            return False
        return secrets.compare_digest(expected, token)

    async def handle_drilldown(self, session_id: str, prompt: str) -> str:
        handler = self._handlers.get(session_id)
        if handler is None:
            raise SessionNotFoundError(session_id)
        return await handler(prompt)


def create_app(session_bridge: DashboardSessionBridge | None = None) -> FastAPI:
    app = FastAPI(title="Yigthinker Dashboard API")

    entries: list[dict[str, Any]] = []
    ws_connections: list[WebSocket] = []

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/dashboard/entries")
    async def list_entries():
        return entries

    @app.post("/api/dashboard/push")
    async def push_entry(entry: DashboardEntry):
        data = entry.model_dump()
        entries.append(data)
        dead = []
        for ws in ws_connections:
            try:
                await ws.send_json({"type": "new_entry", "entry": data})
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_connections.remove(ws)
        return {"ok": True, "dashboard_id": entry.dashboard_id}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        # Validate Origin header to block cross-origin browser-based connections.
        origin = ws.headers.get("origin", "")
        if origin and origin not in _ALLOWED_ORIGINS:
            await ws.close(code=4403, reason="Cross-origin WebSocket connections not allowed")
            return

        await ws.accept()
        ws_connections.append(ws)
        await ws.send_json({"type": "init", "entries": entries})
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                if msg.get("type") != "drilldown":
                    await ws.send_json({"type": "ack", "message": "message received"})
                    continue

                session_id = str(msg.get("session_id", "")).strip()
                prompt = str(msg.get("prompt", "")).strip()
                token = str(msg.get("token", "")).strip()

                if not session_bridge or not session_id or not prompt:
                    await ws.send_json({"type": "ack", "message": "drilldown received"})
                    continue

                # Require a valid per-session auth token on every drilldown.
                if not token or not session_bridge.verify_token(session_id, token):
                    await ws.send_json(
                        {
                            "type": "drilldown_error",
                            "session_id": session_id,
                            "message": "Invalid or missing drilldown token",
                        }
                    )
                    continue

                try:
                    result = await session_bridge.handle_drilldown(session_id, prompt)
                    await ws.send_json(
                        {
                            "type": "drilldown_result",
                            "session_id": session_id,
                            "prompt": prompt,
                            "result": result,
                        }
                    )
                except SessionNotFoundError:
                    await ws.send_json(
                        {
                            "type": "drilldown_error",
                            "session_id": session_id,
                            "message": f"Active session '{session_id}' not found",
                        }
                    )
        except WebSocketDisconnect:
            if ws in ws_connections:
                ws_connections.remove(ws)

    return app
