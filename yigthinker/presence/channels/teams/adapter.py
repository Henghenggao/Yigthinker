"""Microsoft Teams channel adapter (Bot Framework REST API).

Uses raw HTTP via ``httpx`` + ``msal`` for Azure AD token acquisition.
Inbound requests support either Bot Framework bearer JWTs or legacy
Outgoing Webhook HMAC signatures.

Requires: ``pip install httpx msal PyJWT[crypto]``
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from yigthinker.presence.channels.artifacts import (
    choose_best_artifact,
    structured_artifact_from_tool_result,
)
from yigthinker.presence.channels.teams.auth import TeamsAuthValidator
from yigthinker.presence.channels.teams.cards import TeamsCardRenderer
from yigthinker.presence.gateway.session_key import SessionKey

if TYPE_CHECKING:
    from yigthinker.presence.gateway.server import GatewayServer
    from yigthinker.presence.channels.command_parser import ChannelCommand
    from yigthinker.session import SessionContext

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".json", ".parquet"}

# quick-260416-kyn: suffixes we actively deliver back to Teams as a signed-
# URL download. Matches RESEARCH.md §"Keep text artifacts card-only": .py /
# .md / .sql / .txt stay card-only (user copy-pastes or scrolls inline).
_DELIVERABLE_SUFFIXES = frozenset({".xlsx", ".xls", ".csv", ".pdf", ".docx", ".png"})
_DELIVERABLE_MIME_PREFIXES = (
    "application/vnd.openxmlformats",
    "application/pdf",
)


def _sanitize_attachment_name(name: str) -> str:
    candidate = str(name).strip()
    basename = PureWindowsPath(PurePosixPath(candidate).name).name
    if not basename or basename in {".", ".."}:
        return "attachment"
    return basename


class TeamsAdapter:
    """Teams channel adapter using Bot Framework REST API.

    Uses:
      - ``httpx`` for HTTP requests to Bot Framework service URL
      - ``msal`` for Azure AD token acquisition
      - Bot Framework bearer JWTs for standard Teams bot apps
      - HMAC verification for legacy Teams Outgoing Webhooks
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
        self._auth_validator = TeamsAuthValidator(
            client_id=self._client_id,
            webhook_secret=self._webhook_secret,
            timeout=min(self._timeout, 5.0),
        )
        self._gateway: GatewayServer | None = None
        self._msal_app: Any = None

    async def start(self, gateway: GatewayServer) -> None:
        self._gateway = gateway

        if not self._webhook_secret:
            logger.warning(
                "Teams webhook_secret is empty - legacy Outgoing Webhook "
                "HMAC validation is disabled. Standard Teams bot traffic can "
                "still authenticate with Bot Framework bearer tokens."
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
            # Read raw body before JSON parsing so HMAC validation, when used,
            # sees the exact bytes that Teams signed.
            raw_body = await request.body()
            auth_header = request.headers.get("Authorization", "")
            if not await self._auth_validator.authenticate(raw_body, auth_header):
                return JSONResponse({"error": "unauthorized"}, status_code=401)

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
            # Bot Framework bots must 200-OK the webhook with an empty body.
            # Inline Activity attachments in the webhook response (the legacy
            # Outgoing-Webhook trick) render as "cards.unsupported" on modern
            # Teams clients — see quick-260416-j3y follow-up. Progress is
            # conveyed via the typing indicator (_typing_loop) and the final
            # card is pushed via the Bot Framework activities API.
            asyncio.create_task(
                self._process_and_respond(key, text, body, file_attachments)
            )

            return JSONResponse({})

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
        artifact: dict[str, Any] | None = None,
    ) -> None:
        """Send response to Teams via Bot Framework REST API with Adaptive Card."""
        if error:
            card = self._renderer.render_error(error)
        elif artifact is not None:
            card = self._build_card_for_artifact(text or "", artifact)
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

    async def deliver_artifact(
        self,
        event: dict[str, Any],
        artifact: dict[str, Any],
    ) -> None:
        """Phase 1b: deliver an artifact via the existing send_response path."""
        await self.send_response(event, "", artifact=artifact)

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

    def _is_deliverable(self, path_str: str, mime: str) -> bool:
        """Should this file artifact be offered as a Teams download?

        Binary artifacts (xlsx/pdf/docx/png/csv) → yes. Text scripts
        (.py/.md/.sql/.txt) → no, keep card-only. See RESEARCH.md §"Keep
        text artifacts card-only".
        """
        if not path_str:
            return False
        suffix = Path(path_str).suffix.lower()
        if suffix in _DELIVERABLE_SUFFIXES:
            return True
        if mime:
            return any(mime.startswith(pfx) for pfx in _DELIVERABLE_MIME_PREFIXES)
        return False

    def _is_public_base_url(self, url: str) -> bool:
        """Is this URL reachable from the Teams client (not loopback)?

        Loopback hosts (127.*, localhost, 0.0.0.0) fail because the Teams
        service fetches the URL from Microsoft's cloud and cannot hit the
        gateway's local interface. LAN / ngrok / real DNS names are fine.
        """
        if not url:
            return False
        lower = url.lower()
        if lower.startswith(("http://127.", "http://localhost", "http://0.0.0.0")):
            return False
        if lower.startswith(("https://127.", "https://localhost", "https://0.0.0.0")):
            return False
        return lower.startswith(("http://", "https://"))

    def _append_text_to_card(self, card: dict[str, Any], text: str) -> dict[str, Any]:
        if text.strip():
            card.setdefault("body", []).append(
                {"type": "TextBlock", "text": text, "wrap": True}
            )
        return card

    def _build_chart_card(self, artifact: dict[str, Any]) -> dict[str, Any]:
        from yigthinker.presence.gateway.server import CHART_CACHE_DIR
        from yigthinker.visualization.exporter import ChartExporter

        chart_id = uuid.uuid4().hex
        CHART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CHART_CACHE_DIR / f"{chart_id}.json").write_text(
            artifact["chart_json"], encoding="utf-8"
        )

        base_url = self._gateway_base_url()
        png_url = f"{base_url}/api/charts/{chart_id}.png"
        interactive_url = f"{base_url}/api/charts/{chart_id}"

        try:
            png_bytes = ChartExporter().to_png(artifact["chart_json"])
            (CHART_CACHE_DIR / f"{chart_id}.png").write_bytes(png_bytes)
        except Exception:
            logger.debug("Teams PNG export unavailable; falling back to chart link", exc_info=True)
            return self._renderer.render_chart_link(
                artifact["chart_name"],
                interactive_url,
                description="Interactive chart preview",
            )

        return self._renderer.render_chart_image(
            artifact["chart_name"],
            png_url,
            interactive_url=interactive_url,
        )

    def _build_card_for_artifact(
        self,
        text: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if artifact.get("kind") == "chart":
                return self._append_text_to_card(self._build_chart_card(artifact), text)
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
                # artifact_write / excel_write output.
                # quick-260416-kyn: for deliverable binary artifacts
                # (xlsx/pdf/docx/etc.) issue a signed download URL via the
                # gateway's FileTokenStore and surface it as Action.OpenUrl.
                # For text artifacts (.py/.md/.sql) stay card-only — there
                # is no user win in forcing a browser round-trip for content
                # that is already human-readable.
                download_url: str | None = None
                path_str = artifact.get("path") or ""
                mime = artifact.get("mime_type") or ""
                if path_str and self._is_deliverable(path_str, mime):
                    base_url = self._gateway_base_url()
                    token_store = getattr(
                        self._gateway, "_file_token_store", None,
                    )
                    if token_store is not None and self._is_public_base_url(base_url):
                        try:
                            from urllib.parse import quote
                            token = token_store.issue(Path(path_str).resolve())
                            name_q = quote(
                                artifact.get("filename") or Path(path_str).name,
                                safe="",
                            )
                            download_url = (
                                f"{base_url}/api/files/{token}?name={name_q}"
                            )
                        except Exception:
                            logger.exception(
                                "Failed to issue download token for Teams outbound file",
                            )
                            download_url = None
                return self._append_text_to_card(
                    self._renderer.render_file_saved(
                        artifact["filename"],
                        int(artifact.get("bytes") or 0),
                        summary=artifact.get("summary"),
                        download_url=download_url,
                    ),
                    text,
                )
        except Exception:
            logger.exception("Failed to build Teams structured response card; falling back to text")
        return self._renderer.render_text(text)

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
                # Resolve (or eagerly create/restore) the live session so
                # downloaded temp paths can be allowlisted via ctx.attachments.
                # Mirrors handle_message's flow at server.py:233-234
                # (get_active_key → get_or_restore) so first-message attachment
                # uploads also get allowlist coverage — get_or_restore is
                # idempotent, so the later handle_message() call reuses it.
                ctx_for_registration: "SessionContext | None" = None
                try:
                    active_key = self._gateway.registry.get_active_key(session_key)
                    managed = await self._gateway.registry.get_or_restore(
                        active_key, self._gateway._settings, "teams"
                    )
                    ctx_for_registration = managed.ctx
                except Exception:
                    logger.exception(
                        "Failed to resolve session for attachment registration"
                    )
                file_lines, error_lines = await self._download_attachments(
                    file_attachments, ctx=ctx_for_registration
                )
                prefix_parts = file_lines + error_lines
                if prefix_parts:
                    prefix = "\n".join(prefix_parts)
                    text = f"{prefix}\n{text}" if text else prefix

            if not text:
                return

            # P1-2: route slash commands before sending to agent
            from yigthinker.presence.channels.command_parser import parse_channel_command
            cmd = parse_channel_command(text)
            if cmd is not None:
                cmd_result = await self._handle_command(cmd, session_key, event)
                await self.send_response(event, cmd_result)
                return

            # --- Phase 2: agent processing with progress callbacks ---
            _tool_names: dict[str, str] = {}
            artifacts: list[dict[str, Any]] = []

            def _on_teams_tool_event(event_type: str, data: dict) -> None:
                if event_type == "tool_call":
                    _tool_names[data.get("tool_id", "")] = data.get("tool_name", "tool")
                elif event_type == "tool_result" and not data.get("is_error"):
                    artifact = structured_artifact_from_tool_result(data.get("content_obj"))
                    if artifact is not None:
                        artifacts.append(artifact)
                    # Progress cards intentionally disabled: the typing
                    # indicator + final natural-language response (which the
                    # system prompt instructs the agent to narrate) already
                    # convey progress without JSON-looking clutter.

            # Task 14/15: extract replied-to message for context emphasis.
            # Best-effort: a failed fetch returns []; we never block the send.
            try:
                quoted = await self.extract_quoted_messages(event)
            except Exception:
                logger.exception("Teams quote extraction failed; continuing without")
                quoted = []

            result = await self._gateway.handle_message(
                session_key, text, channel="teams",
                on_tool_event=_on_teams_tool_event,
                quoted_messages=quoted or None,
            )
            await self.send_response(
                event,
                result,
                artifact=choose_best_artifact(artifacts),
            )
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

    async def _handle_command(self, cmd: "ChannelCommand", session_key: str, event: dict[str, Any]) -> str:
        """Handle a slash command from a Teams user."""
        registry = self._gateway.registry
        if cmd.name == "new":
            label = cmd.args[0] if cmd.args else None
            # Sanitize label: alphanumeric, underscore, hyphen only
            if label and not re.fullmatch(r"[a-zA-Z0-9_\-]{1,32}", label):
                return "Session name must be alphanumeric/underscore/hyphen, max 32 chars."
            new_key = f"{session_key}:{label}" if label else f"{session_key}:new"
            registry.set_active_key(session_key, new_key)
            return f"Started new session{': ' + label if label else ''}."
        elif cmd.name == "sessions":
            sessions = registry.list_sessions_for_owner(session_key)
            if not sessions:
                return "No active sessions."
            lines = [f"- {s['key']} (idle: {s.get('idle_seconds', 'unknown')}s)" for s in sessions]
            return "Active sessions:\n" + "\n".join(lines)
        elif cmd.name == "switch":
            target = cmd.args[0] if cmd.args else None
            if not target:
                return "Usage: /switch <session-name>"
            # Security: target must be scoped to the sender's own namespace
            if target != session_key and not target.startswith(session_key + ":"):
                return f"Cannot switch to '{target}': you can only switch between your own sessions."
            registry.set_active_key(session_key, target)
            return f"Switched to session: {target}"
        elif cmd.name == "undo":
            return "File undo is available via the agent. Ask: 'undo my last file change'."
        elif cmd.name == "branch":
            label = cmd.args[0] if cmd.args else None
            return "Session branching is available via the SDK. Use sdk.branch() in your integration."
        return f"Unknown command: /{cmd.name}"

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
        self,
        attachments: list[dict[str, Any]],
        ctx: "SessionContext | None" = None,
    ) -> tuple[list[str], list[str]]:
        """Download file attachments to temp dir.

        Returns (file_lines, error_lines) where:
          file_lines = ["[Attached file: name.xlsx -> /path/to/name.xlsx]", ...]
          error_lines = ["[Skipped unsupported file: x.pdf (...)]", ...]

        When ``ctx`` is provided, each successfully-downloaded destination path
        (resolved, absolute) is added to ``ctx.attachments`` so that df_load /
        report_generate accept it even though it sits outside workspace_dir.
        ``ctx=None`` preserves legacy call shape for existing tests.
        """
        file_lines: list[str] = []
        error_lines: list[str] = []
        supported_str = ", ".join(sorted(_SUPPORTED_EXTENSIONS))

        for att in attachments:
            raw_name = att.get("name", "unknown")
            name = _sanitize_attachment_name(raw_name)
            if name != raw_name:
                logger.warning(
                    "Sanitized Teams attachment name '%s' to '%s'",
                    raw_name,
                    name,
                )

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

                if ctx is not None:
                    try:
                        ctx.attachments.add(dest.resolve())
                    except Exception:
                        logger.warning(
                            "Failed to register Teams attachment in "
                            "ctx.attachments: %s", name,
                        )

                file_lines.append(
                    f"[Attached file: {name} -> {dest}]"
                )
            except Exception as exc:
                logger.warning(
                    "Failed to download Teams attachment '%s': %s", name, exc
                )
                error_lines.append(f"[Failed to download: {name}]")

        return file_lines, error_lines

    async def extract_quoted_messages(self, event: dict[str, Any]) -> list[Any]:
        """Extract the quoted/replied-to message via Bot Framework reply-to-id.

        When a Teams user replies to a prior message, the activity carries a
        ``replyToId`` field. We fetch the original activity from:
        ``{serviceUrl}v3/conversations/{conversationId}/activities/{replyToId}``
        using an MSAL-acquired bearer token.

        Best-effort: any failure (missing IDs, non-200, network error) returns
        an empty list rather than raising.
        """
        from yigthinker.session import QuotedMessage

        reply_to_id = event.get("replyToId")
        if not reply_to_id:
            return []

        conversation_id = event.get("conversation", {}).get("id", "")
        if not conversation_id:
            return []

        service_url = (
            event.get("serviceUrl")
            or self._service_url_override
            or ""
        )
        if not service_url:
            return []
        if not service_url.endswith("/"):
            service_url += "/"

        try:
            token = self._acquire_token()
            if not token:
                return []
            url = (
                f"{service_url}v3/conversations/"
                f"{conversation_id}/activities/{reply_to_id}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
            if resp.status_code != 200:
                return []
            original = resp.json()
            original_text = original.get("text", "") or ""
            from_id = original.get("from", {}).get("id", "") or ""
            # Bot Framework sends activities with from.id typically in the form
            # "28:<client_id>". Match either exact or contains client_id.
            is_bot = bool(
                self._client_id
                and (from_id == self._client_id or self._client_id in from_id)
            )
            original_role = "assistant" if is_bot else "user"
            return [QuotedMessage(
                original_id=str(reply_to_id),
                original_text=original_text,
                original_role=original_role,
            )]
        except Exception:
            return []

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
