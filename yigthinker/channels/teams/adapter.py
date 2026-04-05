"""Microsoft Teams channel adapter (Graph API, not deprecated Bot Framework SDK).

Uses raw HTTP via ``httpx`` + ``msal`` for Azure AD token acquisition.
Marked as optional/experimental.

Requires: ``pip install httpx msal``
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from yigthinker.channels.teams.cards import TeamsCardRenderer
from yigthinker.channels.teams.hmac import verify_teams_hmac_signature
from yigthinker.gateway.session_key import SessionKey

if TYPE_CHECKING:
    from yigthinker.gateway.server import GatewayServer

logger = logging.getLogger(__name__)


class TeamsAdapter:
    """Teams channel adapter using Microsoft Graph API.

    Instead of the deprecated ``botbuilder-core`` SDK, this adapter uses:
      - ``httpx`` for HTTP requests to the Graph API
      - ``msal`` for Azure AD token acquisition
      - Outgoing Webhook for inbound messages (HMAC-SHA256 signature verification)
    """

    name = "teams"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._tenant_id = config.get("tenant_id", "")
        self._client_id = config.get("client_id", "")
        self._client_secret = config.get("client_secret", "")
        self._webhook_secret = config.get("webhook_secret", "")
        self._session_scope = config.get("session_scope", "per-sender")
        self._renderer = TeamsCardRenderer()
        self._gateway: GatewayServer | None = None
        self._msal_app: Any = None

    async def start(self, gateway: GatewayServer) -> None:
        self._gateway = gateway

        try:
            import msal
            self._msal_app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._client_secret,
            )
        except ImportError:
            logger.error("msal not installed. Run: pip install msal")
            return

        @gateway.app.post("/webhook/teams")
        async def teams_webhook(request: Request):
            # HMAC verification per D-06 -- must read raw body BEFORE JSON parsing
            raw_body = await request.body()
            if self._webhook_secret:
                auth_header = request.headers.get("Authorization", "")
                if not verify_teams_hmac_signature(
                    raw_body, auth_header, self._webhook_secret
                ):
                    return JSONResponse(
                        {"error": "Invalid HMAC signature"}, status_code=401
                    )

            body = json.loads(raw_body)
            text = body.get("text", "").strip()
            if not text:
                return JSONResponse({"type": "message", "text": "Empty message"})

            key = self.session_key(body)

            # Per D-05: Immediate ACK + async processing
            # Return 200 immediately with a "thinking..." card.
            # Fire async task to process and deliver result via Graph API.
            asyncio.create_task(self._process_and_respond(key, text, body))

            return JSONResponse({
                "type": "message",
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": self._renderer.render_thinking(),
                }],
            })

        logger.info("Teams adapter registered at /webhook/teams")

    async def stop(self) -> None:
        pass

    def session_key(self, event: dict[str, Any]) -> str:
        sender_id = event.get("from", {}).get("aadObjectId", "unknown")
        if self._session_scope == "per-channel":
            channel_id = (
                event.get("channelData", {}).get("channel", {}).get("id", "")
            )
            if channel_id:
                return SessionKey.per_channel("teams", channel_id)
        return SessionKey.per_sender("teams", sender_id)

    async def send_response(
        self,
        event: dict[str, Any],
        text: str | None,
        vars_summary: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        """Send response to Teams via Bot Framework REST API with Adaptive Card.

        Uses MSAL ConfidentialClientApplication to acquire an app token,
        then POSTs an Adaptive Card to the conversation via Bot Framework API.
        """
        if error:
            card = self._renderer.render_error(error)
        elif text:
            card = self._renderer.render_text(text)
        else:
            return

        # Extract conversation context from the original event
        service_url = event.get(
            "serviceUrl", "https://smba.trafficmanager.net/amer/"
        )
        conversation_id = event.get("conversation", {}).get("id", "")
        if not conversation_id:
            logger.error(
                "No conversation ID in Teams event -- cannot send response"
            )
            return

        # Acquire Bot Framework API token via MSAL
        token = self._acquire_token()
        if not token:
            logger.error("Failed to acquire MSAL token for Bot Framework API")
            return

        # POST Adaptive Card to the conversation via Bot Framework REST API
        # (Teams outgoing webhooks use the Bot Framework service URL,
        # not Graph API directly)
        url = (
            f"{service_url.rstrip('/')}/v3/conversations/"
            f"{conversation_id}/activities"
        )
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                logger.error(
                    "Teams Bot Framework API error %d: %s",
                    resp.status_code,
                    resp.text,
                )

    async def _process_and_respond(
        self, session_key: str, text: str, event: dict[str, Any]
    ) -> None:
        """Run agent processing asynchronously and deliver result via Graph API (D-05)."""
        try:
            result = await self._gateway.handle_message(
                session_key, text, channel="teams"
            )
            await self.send_response(event, result)
        except Exception:
            logger.exception("Error processing Teams message")
            try:
                await self.send_response(
                    event, None, error="Internal processing error"
                )
            except Exception:
                logger.exception("Failed to send error card to Teams")

    def _acquire_token(self) -> str | None:
        """Acquire an app-only token via MSAL for Bot Framework API calls."""
        if self._msal_app is None:
            return None
        result = self._msal_app.acquire_token_for_client(
            scopes=["https://api.botframework.com/.default"],
        )
        if "access_token" in result:
            return result["access_token"]
        logger.error(
            "MSAL token acquisition failed: %s",
            result.get("error_description", ""),
        )
        return None
