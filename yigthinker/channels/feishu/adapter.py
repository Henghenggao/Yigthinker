"""Feishu/Lark channel adapter.

Handles webhook event subscription, signature verification, 3-second ACK,
async background processing, and interactive card update pattern.

Requires: ``pip install lark-oapi``
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse

from yigthinker.channels.artifacts import (
    choose_best_artifact,
    structured_artifact_from_tool_result,
)
from yigthinker.channels.feishu.cards import FeishuCardRenderer
from yigthinker.channels.feishu.dedup import EventDeduplicator
from yigthinker.gateway.session_key import SessionKey

if TYPE_CHECKING:
    from yigthinker.gateway.server import GatewayServer

logger = logging.getLogger(__name__)


def _extract_message_text_from_content(content: str) -> str:
    """Best-effort extraction of human-readable text from Feishu message body."""
    if not content:
        return ""
    try:
        parsed = json.loads(content)
    except Exception:
        return content

    if isinstance(parsed, dict):
        text = parsed.get("text")
        if isinstance(text, str):
            return text
    return content


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

            if not self._verify_token:
                # Fail-closed: reject all requests if verification_token is not
                # configured, matching Teams adapter behavior. Operators must set
                # verification_token to enable the webhook.
                return JSONResponse({"code": 99991663, "msg": "verification token not configured"}, status_code=401)
            incoming_token = body.get("token") or body.get("header", {}).get("token", "")
            if not incoming_token or incoming_token != self._verify_token:
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
        artifact: dict[str, Any] | None = None,
    ) -> None:
        """Send a card response back to the Feishu chat."""
        if not self._client:
            return

        sender = event.get("event", {}).get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        if not sender_id:
            return

        card = self._build_card_for_artifact(text, artifact)
        await self._send_card(sender_id, card)

    def _gateway_base_url(self) -> str:
        gw_cfg = getattr(self._gateway, "_settings", {}).get("gateway", {})
        public_base_url = gw_cfg.get("public_base_url", "")
        if public_base_url:
            return public_base_url.rstrip("/")

        host = gw_cfg.get("host", "127.0.0.1")
        if host in {"", "0.0.0.0", "::"}:
            host = "127.0.0.1"
        port = gw_cfg.get("port", 8766)
        scheme = gw_cfg.get("scheme", "http")
        return f"{scheme}://{host}:{port}"

    def _append_text_to_card(self, card: dict[str, Any], text: str) -> dict[str, Any]:
        if text.strip():
            card.setdefault("elements", []).append({"tag": "markdown", "content": text})
        return card

    def _build_card_for_artifact(
        self,
        text: str,
        artifact: dict[str, Any] | None,
    ) -> dict[str, Any]:
        chart_id = ""
        if artifact is None:
            return self._renderer.render_text(text)

        try:
            if artifact.get("kind") == "chart":
                from yigthinker.gateway.server import CHART_CACHE_DIR
                from yigthinker.visualization.exporter import ChartExporter

                chart_id = artifact["chart_name"].replace(" ", "-") or "chart"
                # Use uuid4 (not id()) so chart IDs are unguessable and don't
                # collide across sessions or after GC reuses memory addresses.
                chart_id = f"{chart_id}-{uuid.uuid4().hex}"
                CHART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                # Contain the write path to CHART_CACHE_DIR (path traversal guard).
                target = (CHART_CACHE_DIR / f"{chart_id}.json").resolve()
                if not str(target).startswith(str(CHART_CACHE_DIR.resolve())):
                    raise ValueError(f"chart_id '{chart_id}' resolves outside cache dir")
                target.write_text(artifact["chart_json"], encoding="utf-8")

                spec = ChartExporter().to_vchart(artifact["chart_json"])
                return self._append_text_to_card(
                    self._renderer.render_vchart_native(artifact["chart_name"], spec),
                    text,
                )
        except Exception:
            logger.debug("Feishu VChart export unavailable; falling back to chart link", exc_info=True)
            html_url = f"{self._gateway_base_url()}/api/charts/{chart_id}"
            return self._append_text_to_card(
                self._renderer.render_chart_link(
                    artifact["chart_name"],
                    html_url,
                    description="Interactive chart preview",
                ),
                text,
            )

        if artifact.get("kind") == "table":
            return self._append_text_to_card(
                self._renderer.render_native_table(
                    artifact["title"],
                    artifact["columns"],
                    artifact["rows"],
                    artifact["total_rows"],
                ),
                text,
            )

        if artifact.get("kind") == "file":
            return self._append_text_to_card(
                self._renderer.render_file_saved(
                    artifact["filename"],
                    int(artifact.get("bytes") or 0),
                    summary=artifact.get("summary"),
                ),
                text,
            )

        return self._renderer.render_text(text)

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

            # P1-2: route slash commands
            from yigthinker.channels.command_parser import parse_channel_command
            cmd = parse_channel_command(text)
            if cmd is not None:
                await self.send_response(body, f"Command /{cmd.name} received. Slash commands are processed by the agent.")
                return

            key = self.session_key(body)
            sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
            artifacts: list[dict[str, Any]] = []

            # Step 1: Send "thinking..." card
            thinking_msg_id = await self._send_card(
                sender_id, self._renderer.render_thinking()
            )

            def _on_feishu_tool_event(event_type: str, data: dict) -> None:
                if event_type != "tool_result" or data.get("is_error"):
                    return
                artifact = structured_artifact_from_tool_result(data.get("content_obj"))
                if artifact is not None:
                    artifacts.append(artifact)

            try:
                quoted = await self.extract_quoted_messages(body)
            except Exception:
                logger.exception("Feishu quote extraction failed; continuing without")
                quoted = []

            # Step 2: Run agent
            result = await self._gateway.handle_message(
                key,
                text,
                channel="feishu",
                on_tool_event=_on_feishu_tool_event,
                quoted_messages=quoted or None,
            )

            # Steering acknowledged — the message was routed to the live
            # steering queue of a running agent. No response card to render;
            # the running agent will surface the result via its own card.
            if result is None:
                return

            # Step 3: Update the card with the result
            result_card = self._build_card_for_artifact(
                result,
                choose_best_artifact(artifacts),
            )
            if thinking_msg_id:
                await self._update_card(thinking_msg_id, result_card)
            else:
                await self._send_card(sender_id, result_card)

        except Exception:
            logger.exception("Error processing Feishu event")

    async def extract_quoted_messages(self, event: dict[str, Any]) -> list[Any]:
        """Fetch the replied-to / parent message when Feishu supplies linkage IDs."""
        from yigthinker.session import QuotedMessage

        if not self._client:
            return []

        message = (event.get("event") or {}).get("message", {})
        current_id = message.get("message_id", "")
        quoted_id = (
            message.get("parent_id")
            or message.get("upper_message_id")
            or ""
        )
        root_id = message.get("root_id", "")
        if not quoted_id and root_id and root_id != current_id:
            quoted_id = root_id
        if not quoted_id:
            return []

        try:
            from lark_oapi.api.im.v1 import GetMessageRequest

            request = GetMessageRequest.builder().message_id(quoted_id).build()
            response = await asyncio.to_thread(self._client.im.v1.message.get, request)
            if not response.success():
                return []

            items = getattr(getattr(response, "data", None), "items", None) or []
            if not items:
                return []

            original = items[0]
            body = getattr(original, "body", None)
            content = getattr(body, "content", "") if body is not None else ""
            original_text = _extract_message_text_from_content(content)
            sender = getattr(original, "sender", None)
            sender_type = (getattr(sender, "sender_type", "") or "").lower()
            sender_id = getattr(sender, "id", "") or ""
            is_bot = sender_type in {"app", "bot"} or bool(
                self._app_id and sender_id == self._app_id
            )
            original_role = "assistant" if is_bot else "user"

            return [QuotedMessage(
                original_id=str(quoted_id),
                original_text=original_text,
                original_role=original_role,
            )]
        except Exception:
            return []

    async def _send_card(self, receive_id: str, card: dict[str, Any]) -> str | None:
        """Send an interactive card via Feishu API. Returns message_id."""
        if not self._client:
            return None

        try:
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
