"""WebSocket client with automatic reconnection for TUI ↔ Gateway communication."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from yigthinker.gateway.protocol import (
    AttachMsg,
    AuthMsg,
    UserInputMsg,
    to_json_dict,
)

logger = logging.getLogger(__name__)


class GatewayWSClient:
    """Async WebSocket client with exponential backoff reconnection.

    Designed to run as a Textual ``worker``.  Messages received from the
    gateway are dispatched to ``on_message`` callback.
    """

    def __init__(
        self,
        url: str,
        token: str,
        on_message: Callable[[dict[str, Any]], Any] | None = None,
        on_state_change: Callable[[str], Any] | None = None,
    ) -> None:
        self._url = url
        self._token = token
        self._on_message = on_message
        self._on_state_change = on_state_change
        self._ws: Any = None
        self._connected = asyncio.Event()
        self._state = "disconnected"

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str) -> None:
        self._state = state
        if self._on_state_change:
            self._on_state_change(state)

    async def connect_loop(self) -> None:
        """Main connection loop with exponential backoff reconnection."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed. Run: pip install websockets")
            return

        delay = 1.0
        while True:
            try:
                self._set_state("connecting")
                async with websockets.connect(self._url) as ws:
                    self._ws = ws
                    delay = 1.0  # Reset on successful connect

                    # Authenticate
                    await ws.send(json.dumps(to_json_dict(AuthMsg(token=self._token))))
                    raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    auth_result = json.loads(raw)
                    if self._on_message:
                        self._on_message(auth_result)
                    if not auth_result.get("ok"):
                        logger.error("Gateway auth failed: %s", auth_result.get("message"))
                        self._set_state("auth_failed")
                        return  # Don't reconnect on auth failure

                    self._set_state("connected")
                    self._connected.set()
                    await self._read_loop(ws)

            except Exception as exc:
                self._connected.clear()
                self._ws = None
                self._set_state("reconnecting")
                logger.debug("WS disconnected (%s), retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)

    async def _read_loop(self, ws: Any) -> None:
        """Read messages from the WebSocket and dispatch to callback."""
        async for raw in ws:
            try:
                data = json.loads(raw)
                if self._on_message:
                    self._on_message(data)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from gateway: %s", raw[:100])

    async def send_input(self, text: str, request_id: str = "") -> None:
        """Send a user input message to the gateway."""
        await self._wait_connected()
        msg = to_json_dict(UserInputMsg(text=text, request_id=request_id))
        await self._ws.send(json.dumps(msg))

    async def attach_session(self, session_key: str) -> None:
        """Attach to a session on the gateway."""
        await self._wait_connected()
        msg = to_json_dict(AttachMsg(session_key=session_key))
        await self._ws.send(json.dumps(msg))

    async def send_raw(self, data: dict[str, Any]) -> None:
        """Send a raw JSON message to the gateway."""
        await self._wait_connected()
        await self._ws.send(json.dumps(data))

    async def _wait_connected(self) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout=10.0)
