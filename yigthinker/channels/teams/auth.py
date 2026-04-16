"""Inbound authentication helpers for Microsoft Teams activities.

Supports both:
  - Teams Outgoing Webhook HMAC signatures
  - Bot Framework bearer JWTs for standard Teams bot apps
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from yigthinker.channels.teams.hmac import verify_teams_hmac_signature

logger = logging.getLogger(__name__)

_BOTFRAMEWORK_OPENID_URL = (
    "https://login.botframework.com/v1/.well-known/openidconfiguration"
)
_BOTFRAMEWORK_ISSUER = "https://api.botframework.com"
_JWKS_CACHE_TTL_SECONDS = 24 * 60 * 60


def _select_endorsed_key(
    keys: list[dict[str, Any]],
    kid: str,
    channel_id: str,
) -> dict[str, Any] | None:
    for key in keys:
        if key.get("kid") != kid:
            continue
        endorsements = key.get("endorsements")
        if not isinstance(endorsements, list):
            continue
        if channel_id in endorsements:
            return key
    return None


class TeamsAuthValidator:
    """Validate inbound Teams requests across supported auth modes."""

    def __init__(
        self,
        *,
        client_id: str,
        webhook_secret: str,
        timeout: float = 5.0,
    ) -> None:
        self._client_id = client_id
        self._webhook_secret = webhook_secret
        self._timeout = timeout
        self._jwks_uri: str | None = None
        self._jwks_cache: list[dict[str, Any]] | None = None
        self._jwks_expires_at = 0.0
        self._jwks_lock = asyncio.Lock()

    async def authenticate(self, raw_body: bytes, auth_header: str) -> bool:
        auth_header = auth_header.strip()
        if auth_header.startswith("HMAC "):
            return self._authenticate_hmac(raw_body, auth_header)
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            return await self._authenticate_bearer(raw_body, token)
        logger.warning(
            "Teams auth rejected: unsupported Authorization scheme; "
            "expected HMAC or Bearer"
        )
        return False

    def _authenticate_hmac(self, raw_body: bytes, auth_header: str) -> bool:
        if not self._webhook_secret:
            logger.error(
                "Teams auth rejected: received HMAC webhook request but "
                "webhook_secret is not configured"
            )
            return False
        return verify_teams_hmac_signature(
            raw_body, auth_header, self._webhook_secret
        )

    async def _authenticate_bearer(self, raw_body: bytes, token: str) -> bool:
        if not self._client_id:
            logger.error(
                "Teams auth rejected: client_id is required to validate "
                "Bot Framework bearer tokens"
            )
            return False
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("Teams auth rejected: invalid JSON body")
            return False

        service_url = body.get("serviceUrl", "")
        channel_id = body.get("channelId", "")
        if not service_url:
            logger.warning("Teams auth rejected: activity missing serviceUrl")
            return False
        if not channel_id:
            logger.warning("Teams auth rejected: activity missing channelId")
            return False

        try:
            import jwt
        except ImportError:
            logger.error(
                "Teams bearer auth requires PyJWT. Reinstall with the "
                "'teams' extra so bot requests can be verified."
            )
            return False

        try:
            signing_key = await self._resolve_signing_key(
                token=token,
                channel_id=channel_id,
                jwt_module=jwt,
            )
        except Exception:
            logger.warning(
                "Teams auth rejected: failed to refresh Bot Framework signing keys",
                exc_info=True,
            )
            return False
        if signing_key is None:
            return False

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(
                json.dumps(signing_key)
            )
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=_BOTFRAMEWORK_ISSUER,
                options={"require": ["aud", "iss", "exp", "nbf"]},
                leeway=300,
            )
        except Exception:
            logger.warning(
                "Teams auth rejected: Bot Framework bearer token "
                "verification failed",
                exc_info=True,
            )
            return False

        claim_service_url = claims.get("serviceUrl") or claims.get("serviceurl")
        if claim_service_url != service_url:
            logger.warning(
                "Teams auth rejected: bearer token serviceUrl claim mismatch"
            )
            return False
        return True

    async def _resolve_signing_key(
        self,
        *,
        token: str,
        channel_id: str,
        jwt_module: Any,
    ) -> dict[str, Any] | None:
        try:
            header = jwt_module.get_unverified_header(token)
        except Exception:
            logger.warning(
                "Teams auth rejected: malformed bearer token header",
                exc_info=True,
            )
            return None

        kid = header.get("kid")
        if not kid:
            logger.warning("Teams auth rejected: bearer token missing kid")
            return None

        keys = await self._get_jwks(force_refresh=False)
        key = _select_endorsed_key(keys, kid, channel_id)
        if key is not None:
            return key

        keys = await self._get_jwks(force_refresh=True)
        key = _select_endorsed_key(keys, kid, channel_id)
        if key is None:
            logger.warning(
                "Teams auth rejected: no endorsed signing key found for kid=%s "
                "channel=%s",
                kid,
                channel_id,
            )
        return key

    async def _get_jwks(self, *, force_refresh: bool) -> list[dict[str, Any]]:
        now = time.monotonic()
        if (
            not force_refresh
            and self._jwks_cache is not None
            and now < self._jwks_expires_at
        ):
            return self._jwks_cache

        async with self._jwks_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._jwks_cache is not None
                and now < self._jwks_expires_at
            ):
                return self._jwks_cache

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                if self._jwks_uri is None or force_refresh:
                    resp = await client.get(_BOTFRAMEWORK_OPENID_URL)
                    resp.raise_for_status()
                    config = resp.json()
                    self._jwks_uri = str(config["jwks_uri"])

                resp = await client.get(self._jwks_uri)
                resp.raise_for_status()
                payload = resp.json()

            keys = payload.get("keys", [])
            if not isinstance(keys, list):
                raise ValueError("Bot Framework JWKS payload missing keys list")

            self._jwks_cache = [k for k in keys if isinstance(k, dict)]
            self._jwks_expires_at = time.monotonic() + _JWKS_CACHE_TTL_SECONDS
            return self._jwks_cache
