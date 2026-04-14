"""Microsoft Teams channel adapter (Bot Framework REST API).

Uses raw HTTP via ``httpx`` + ``msal`` for Azure AD token acquisition.
Outgoing webhooks verified via HMAC-SHA256.

Requires: ``pip install httpx msal``
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
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

_SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".json", ".parquet"}


class TeamsAdapter:
    """Teams channel adapter using Bot Framework REST API.

    Uses:
      - ``httpx`` for HTTP requests to Bot Framework service URL
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
        self._service_url_override = config.get("service_url", "")
        self._max_retries = int(config.get("max_retries", 3))
        self._timeout = float(config.get("timeout", 30.0))
        self._renderer = TeamsCardRenderer()
        self._gateway: GatewayServer | None = None
        self._msal_app: Any = None

    async def start(self, gateway: GatewayServer) -> None:
        self._gateway = gateway

        # Warn if HMAC verification is disabled
        if not self._webhook_secret:
            logger.warning(
                "Teams webhook_secret is empty — HMAC signature verification "
                "is DISABLED. Set channels.teams.webhook_secret in settings "
                "to secure the webhook endpoint."
            )

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
            # HMAC verification — must read raw body BEFORE JSON parsing
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

            # Extract file attachments (skip inline cards, hero cards, etc.)
            attachments = body.get("attachments", [])
            file_attachments = []
            for a in attachments:
                ct = a.get("contentType", "")
                # Teams file uploads use a special contentType with
                # a pre-authenticated downloadUrl inside content.
                if ct == "application/vnd.microsoft.teams.file.download.info":
                    file_attachments.append(a)
                elif a.get("contentUrl") and ct.startswith(
                    ("application/", "text/")
                ):
                    file_attachments.append(a)

            if not text and not file_attachments:
                return JSONResponse({"type": "message", "text": "Empty message"})

            key = self.session_key(body)

            # Immediate ACK + async processing (D-05):
            # Return 200 immediately with a "thinking..." card.
            # File download + agent processing run in background task
            # so the ACK is never blocked by slow downloads.
            asyncio.create_task(
                self._process_and_respond(key, text, body, file_attachments)
            )

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
        """Send response to Teams via Bot Framework REST API with Adaptive Card."""
        if error:
            card = self._renderer.render_error(error)
        elif text:
            card = self._renderer.render_text(text)
        else:
            return

        # Use configured service_url override for private deployments,
        # fall back to event's serviceUrl, then public cloud default.
        service_url = (
            self._service_url_override
            or event.get("serviceUrl", "")
        )
        if not service_url:
            logger.warning(
                "No serviceUrl in Teams event and no service_url configured. "
                "Set channels.teams.service_url for private deployments."
            )
            service_url = "https://smba.trafficmanager.net/amer/"

        conversation_id = event.get("conversation", {}).get("id", "")
        if not conversation_id:
            logger.error(
                "No conversation ID in Teams event — cannot send response"
            )
            return

        # Acquire Bot Framework API token via MSAL
        token = self._acquire_token()
        if not token:
            logger.error("Failed to acquire MSAL token for Bot Framework API")
            return

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
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Retry with exponential backoff
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code < 400:
                        return  # success
                    if resp.status_code in (429, 500, 502, 503, 504):
                        # Retryable server/rate-limit error
                        logger.warning(
                            "Teams API returned %d (attempt %d/%d): %s",
                            resp.status_code, attempt + 1,
                            self._max_retries, resp.text[:200],
                        )
                        last_error = httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}",
                            request=resp.request, response=resp,
                        )
                    else:
                        # Non-retryable client error (400, 401, 403, etc.)
                        logger.error(
                            "Teams API error %d (not retryable): %s",
                            resp.status_code, resp.text[:200],
                        )
                        return
            except httpx.TimeoutException as exc:
                logger.warning(
                    "Teams API timeout (attempt %d/%d): %s",
                    attempt + 1, self._max_retries, exc,
                )
                last_error = exc
            except httpx.ConnectError as exc:
                logger.warning(
                    "Teams API connection error (attempt %d/%d): %s",
                    attempt + 1, self._max_retries, exc,
                )
                last_error = exc

            if attempt < self._max_retries - 1:
                delay = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(delay)

        logger.error(
            "Teams API failed after %d attempts: %s",
            self._max_retries, last_error,
        )

    async def _send_progress_card(self, event: dict[str, Any], tool_name: str, summary: str) -> None:
        """Fire-and-forget: post a compact progress card to the conversation."""
        try:
            card = self._renderer.render_tool_progress(tool_name, summary)
            service_url = (
                self._service_url_override
                or event.get("serviceUrl", "")
                or "https://smba.trafficmanager.net/amer/"
            )
            conversation_id = event.get("conversation", {}).get("id", "")
            if not conversation_id:
                return
            token = self._acquire_token()
            if not token:
                return
            url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
            payload = {
                "type": "message",
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }],
            }
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(url, json=payload, headers=headers)
        except Exception:
            pass  # progress cards are best-effort

    async def _process_and_respond(
        self,
        session_key: str,
        text: str,
        event: dict[str, Any],
        file_attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Download files, run agent, deliver result via Bot Framework API.

        File download is deferred to this async task so the webhook
        returns the "thinking" card instantly (D-05). Typing indicators
        are sent periodically so the user sees "Bot is typing..." in Teams.
        """
        typing_task = asyncio.create_task(self._typing_loop(event))

        try:
            # --- Phase 1: download attachments (if any) ---
            if file_attachments:
                file_lines, error_lines = await self._download_attachments(
                    file_attachments
                )
                prefix_parts = file_lines + error_lines
                if prefix_parts:
                    prefix = "\n".join(prefix_parts)
                    text = f"{prefix}\n{text}" if text else prefix

            if not text:
                return

            # --- Phase 2: agent processing with progress callbacks ---
            _tool_names: dict[str, str] = {}

            def _on_teams_tool_event(event_type: str, data: dict) -> None:
                if event_type == "tool_call":
                    _tool_names[data.get("tool_id", "")] = data.get("tool_name", "tool")
                elif event_type == "tool_result" and not data.get("is_error"):
                    tool_id = data.get("tool_id", "")
                    tool_name = _tool_names.get(tool_id, "tool")
                    content = data.get("content", "")
                    summary = content[:80] + ("..." if len(content) > 80 else "")
                    asyncio.create_task(
                        self._send_progress_card(event, tool_name, summary)
                    )

            result = await self._gateway.handle_message(
                session_key, text, channel="teams",
                on_tool_event=_on_teams_tool_event,
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
        finally:
            typing_task.cancel()

    async def _typing_loop(self, event: dict[str, Any]) -> None:
        """Send typing indicator every 3 seconds until cancelled."""
        service_url = (
            self._service_url_override
            or event.get("serviceUrl", "")
            or "https://smba.trafficmanager.net/amer/"
        )
        conversation_id = event.get("conversation", {}).get("id", "")
        if not conversation_id:
            return

        token = self._acquire_token()
        if not token:
            return

        url = (
            f"{service_url.rstrip('/')}/v3/conversations/"
            f"{conversation_id}/activities"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"type": "typing"}

        try:
            while True:
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(url, json=payload, headers=headers)
                except Exception:
                    pass
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            return

    async def _download_attachments(
        self, attachments: list[dict[str, Any]]
    ) -> tuple[list[str], list[str]]:
        """Download file attachments to temp dir.

        Returns (file_lines, error_lines) where:
          file_lines = ["[Attached file: name.xlsx -> /path/to/name.xlsx]", ...]
          error_lines = ["[Skipped unsupported file: x.pdf (...)]", ...]
        """
        file_lines: list[str] = []
        error_lines: list[str] = []
        supported_str = ", ".join(sorted(_SUPPORTED_EXTENSIONS))

        for att in attachments:
            name = att.get("name", "unknown")

            # Teams file uploads put a pre-authenticated download URL
            # in content.downloadUrl; fall back to contentUrl for other
            # attachment types (e.g. inline images via Bot Framework).
            content = att.get("content") or {}
            download_url = (
                content.get("downloadUrl")
                if isinstance(content, dict) else None
            ) or att.get("contentUrl", "")

            if not download_url:
                logger.warning(
                    "Teams attachment '%s' has no downloadUrl — skipping", name
                )
                continue

            ext = Path(name).suffix.lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                error_lines.append(
                    f"[Skipped unsupported file: {name} "
                    f"(supported: {supported_str})]"
                )
                continue

            try:
                # content.downloadUrl is pre-authenticated (SharePoint);
                # no Bearer token needed. Only add token for plain
                # contentUrl (Bot Framework hosted attachments).
                headers: dict[str, str] = {}
                if not (isinstance(content, dict) and content.get("downloadUrl")):
                    token = self._acquire_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"

                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True,
                ) as client:
                    resp = await client.get(download_url, headers=headers)
                    resp.raise_for_status()

                tmp_dir = tempfile.mkdtemp(prefix="yigthinker_teams_")
                dest = Path(tmp_dir) / name
                dest.write_bytes(resp.content)

                file_lines.append(
                    f"[Attached file: {name} -> {dest}]"
                )
            except Exception as exc:
                logger.warning(
                    "Failed to download Teams attachment '%s': %s", name, exc
                )
                error_lines.append(f"[Failed to download: {name}]")

        return file_lines, error_lines

    def _acquire_token(self) -> str | None:
        """Acquire an app-only token via MSAL for Bot Framework API calls."""
        if self._msal_app is None:
            logger.error(
                "MSAL app not initialized — check Teams tenant_id, "
                "client_id, and client_secret configuration"
            )
            return None
        result = self._msal_app.acquire_token_for_client(
            scopes=["https://api.botframework.com/.default"],
        )
        if "access_token" in result:
            return result["access_token"]
        logger.error(
            "MSAL token acquisition failed: %s — check Azure AD app "
            "registration and client_secret",
            result.get("error_description", result.get("error", "unknown")),
        )
        return None
