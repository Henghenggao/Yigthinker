"""Google Chat channel adapter.

Handles webhook events from Google Chat spaces.  Requires Google Workspace
(not consumer Gmail) and a service account with Chat API enabled.

Requires: ``pip install google-api-python-client google-auth``
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse

from yigthinker.channels.gchat.cards import GChatCardRenderer
from yigthinker.gateway.session_key import SessionKey

if TYPE_CHECKING:
    from yigthinker.gateway.server import GatewayServer

logger = logging.getLogger(__name__)


def _verify_gchat_token(request: Request, project_number: str) -> bool:
    """Verify the Google Chat webhook Bearer token.

    Google Chat sends a signed JWT in the Authorization header.
    We verify the audience matches our project number and the
    issuer is chat@system.gserviceaccount.com.

    Returns True if the token is valid, False otherwise.
    If google-auth is not installed or project_number is empty,
    logs a warning and returns False.
    """
    if not project_number:
        logger.warning("gchat.project_number not configured, cannot verify webhook token")
        return False

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]

    try:
        from google.oauth2 import id_token  # type: ignore[import]
        from google.auth.transport import requests as google_requests  # type: ignore[import]

        claim = id_token.verify_token(
            token,
            google_requests.Request(),
            audience=project_number,
        )
        # Verify issuer is Google Chat
        if claim.get("iss") != "chat@system.gserviceaccount.com":
            logger.warning("GChat webhook: unexpected issuer %s", claim.get("iss"))
            return False
        return True
    except ImportError:
        logger.error("google-auth not installed, cannot verify GChat webhook token")
        return False
    except Exception:
        logger.warning("GChat webhook token verification failed", exc_info=True)
        return False


class GChatAdapter:
    """Google Chat adapter with webhook handling and Cards v2 responses.

    Limitation: Google Chat enforces 1 request/second per space.
    Uses asyncio.Semaphore per space for outbound rate limiting.
    """

    name = "gchat"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._session_scope = config.get("session_scope", "per-sender")
        self._project_number = config.get("project_number", "")
        self._renderer = GChatCardRenderer()
        self._gateway: GatewayServer | None = None
        self._space_semaphores: dict[str, asyncio.Semaphore] = {}

    async def start(self, gateway: GatewayServer) -> None:
        self._gateway = gateway

        @gateway.app.post("/webhook/gchat")
        async def gchat_webhook(request: Request):
            # Verify Google Chat webhook token (JWT in Authorization header)
            if not _verify_gchat_token(request, self._project_number):
                logger.warning("GChat webhook: token verification failed")
                return JSONResponse({"error": "unauthorized"}, status_code=401)

            body = await request.json()
            event_type = body.get("type", "")

            if event_type == "ADDED_TO_SPACE":
                return JSONResponse({
                    "text": "Yigthinker is ready. Send me a message to start analyzing data."
                })

            if event_type == "MESSAGE":
                text = body.get("message", {}).get("argumentText", "").strip()
                if not text:
                    text = body.get("message", {}).get("text", "").strip()
                if not text:
                    return JSONResponse({"text": "Empty message"})

                key = self.session_key(body)
                space_name = body.get("space", {}).get("name", "default")
                limiter = self._space_semaphores.setdefault(space_name, asyncio.Semaphore(1))

                # Synchronous response: Google Chat expects a reply in the webhook response
                try:
                    async with limiter:
                        result = await asyncio.wait_for(
                            self._gateway.handle_message(key, text, channel="gchat"),
                            timeout=25.0,  # Google Chat webhook timeout is ~30s
                        )
                    return JSONResponse(self._renderer.render_text(result))
                except asyncio.TimeoutError:
                    return JSONResponse(self._renderer.render_text(
                        "Analysis is taking longer than expected. Please try again with a simpler query."
                    ))
                except Exception as exc:
                    logger.exception("Error processing Google Chat event")
                    return JSONResponse(self._renderer.render_error(str(exc)))

            return JSONResponse({"text": ""})

        logger.info("Google Chat adapter registered at /webhook/gchat")

    async def stop(self) -> None:
        pass

    def session_key(self, event: dict[str, Any]) -> str:
        user_name = event.get("user", {}).get("name", "unknown")
        space_name = event.get("space", {}).get("name", "")

        if self._session_scope == "per-channel" and space_name:
            return SessionKey.per_channel("gchat", space_name.replace("/", "_"))

        return SessionKey.per_sender("gchat", user_name.replace("/", "_"))

    async def send_response(
        self,
        event: dict[str, Any],
        text: str,
        vars_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        # Google Chat webhooks use synchronous response — no async send needed
        pass
