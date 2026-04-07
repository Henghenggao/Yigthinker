"""Feishu/Lark channel adapter.

Handles webhook event subscription, signature verification, 3-second ACK,
async background processing, and interactive card update pattern.

Requires: ``pip install lark-oapi``
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse

from yigthinker.channels.feishu.cards import FeishuCardRenderer
from yigthinker.channels.feishu.dedup import EventDeduplicator
from yigthinker.gateway.session_key import SessionKey

if TYPE_CHECKING:
    from yigthinker.gateway.server import GatewayServer

logger = logging.getLogger(__name__)


class FeishuAdapter:
    """Feishu channel adapter with webhook handling and card updates.

    Critical design decisions:
      - ACK within 3 seconds: return ``{"code": 0}`` immediately, process async
      - Event dedup: SQLite-backed ``EventDeduplicator`` (survives restart)
      - Card update: send "thinking..." card → capture ``message_id`` → PATCH result
    """

    name = "feishu"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._app_id = config.get("app_id", "")
        self._app_secret = config.get("app_secret", "")
        self._verify_token = config.get("verification_token", "")
        self._session_scope = config.get("session_scope", "per-sender")
        self._dedup = EventDeduplicator(
            ttl_seconds=config.get("dedup_ttl_seconds", 3600),
        )
        self._renderer = FeishuCardRenderer()
        self._gateway: GatewayServer | None = None
        self._client: Any = None  # lark_oapi.Client

    async def start(self, gateway: GatewayServer) -> None:
        """Register the /webhook/feishu endpoint on the gateway's FastAPI app."""
        self._gateway = gateway

        try:
            import lark_oapi as lark
            self._client = lark.Client.builder() \
                .app_id(self._app_id) \
                .app_secret(self._app_secret) \
                .build()
        except ImportError:
            logger.error("lark-oapi not installed. Run: pip install lark-oapi")
            return

        @gateway.app.post("/webhook/feishu")
        async def feishu_webhook(request: Request):
            body = await request.json()

            if self._verify_token:
                incoming_token = body.get("token") or body.get("header", {}).get("token", "")
                if incoming_token and incoming_token != self._verify_token:
                    return JSONResponse({"code": 99991663, "msg": "verification token mismatch"}, status_code=401)

            # Handle Feishu URL verification challenge
            if body.get("type") == "url_verification":
                return JSONResponse({"challenge": body.get("challenge", "")})

            # Immediately ACK (Feishu requires response within 3 seconds)
            event_id = body.get("header", {}).get("event_id", "")
            if event_id and self._dedup.is_duplicate(event_id):
                logger.debug("Duplicate event %s, skipping", event_id)
                return JSONResponse({"code": 0})

            if event_id:
                self._dedup.record(event_id)

            # Process in background
            asyncio.create_task(self._process_event(body))
            return JSONResponse({"code": 0})

        logger.info("Feishu adapter registered at /webhook/feishu")

    async def stop(self) -> None:
        self._dedup.close()

    def session_key(self, event: dict[str, Any]) -> str:
        """Derive session key from Feishu event."""
        sender = event.get("event", {}).get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "unknown")

        if self._session_scope == "per-channel":
            chat_id = event.get("event", {}).get("message", {}).get("chat_id", "")
            if chat_id:
                return SessionKey.per_channel("feishu", chat_id)

        return SessionKey.per_sender("feishu", sender_id)

    async def send_response(
        self,
        event: dict[str, Any],
        text: str,
        vars_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        """Send a card response back to the Feishu chat."""
        if not self._client:
            return

        sender = event.get("event", {}).get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        if not sender_id:
            return

        card = self._renderer.render_text(text)
        await self._send_card(sender_id, card)

    async def _process_event(self, body: dict[str, Any]) -> None:
        """Background processing of a Feishu message event."""
        if not self._gateway:
            return

        try:
            event = body.get("event", {})
            message = event.get("message", {})
            msg_type = message.get("message_type", "")

            if msg_type != "text":
                logger.debug("Ignoring non-text message type: %s", msg_type)
                return

            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()
            if not text:
                return

            key = self.session_key(body)
            sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

            # Step 1: Send "thinking..." card
            thinking_msg_id = await self._send_card(
                sender_id, self._renderer.render_thinking()
            )

            # Step 2: Run agent
            result = await self._gateway.handle_message(key, text, channel="feishu")

            # Step 3: Update the card with the result
            result_card = self._renderer.render_text(result)
            if thinking_msg_id:
                await self._update_card(thinking_msg_id, result_card)
            else:
                await self._send_card(sender_id, result_card)

        except Exception:
            logger.exception("Error processing Feishu event")

    async def _send_card(self, receive_id: str, card: dict[str, Any]) -> str | None:
        """Send an interactive card via Feishu API. Returns message_id."""
        if not self._client:
            return None

        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("interactive")
                    .content(json.dumps(card))
                    .build()
                ).build()

            response = await asyncio.to_thread(self._client.im.v1.message.create, request)
            if response.success():
                return response.data.message_id
            logger.error("Feishu send failed: %s", response.msg)
            return None
        except Exception:
            logger.exception("Error sending Feishu card")
            return None

    async def _update_card(self, message_id: str, card: dict[str, Any]) -> None:
        """Update an existing interactive card by message_id."""
        if not self._client:
            return

        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

            request = PatchMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(json.dumps(card))
                    .build()
                ).build()

            response = await asyncio.to_thread(self._client.im.v1.message.patch, request)
            if not response.success():
                logger.error("Feishu card update failed: %s", response.msg)
        except Exception:
            logger.exception("Error updating Feishu card")
