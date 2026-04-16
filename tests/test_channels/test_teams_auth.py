"""Tests for Teams inbound auth across HMAC and Bot Framework bearer modes."""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from unittest.mock import patch

from yigthinker.channels.teams.auth import TeamsAuthValidator


def _hmac_auth_header(body: bytes, secret_b64: str) -> str:
    key_bytes = base64.b64decode(secret_b64)
    sig = base64.b64encode(
        hmac_mod.new(key_bytes, body, hashlib.sha256).digest()
    ).decode()
    return f"HMAC {sig}"


def _fake_jwt_module(
    *,
    service_url_claim: str,
    kid: str = "kid-1",
) -> ModuleType:
    module = ModuleType("jwt")
    module.get_unverified_header = lambda token: {"kid": kid, "alg": "RS256"}

    class _RSAAlgorithm:
        @staticmethod
        def from_jwk(_data: str):
            return "fake-public-key"

    module.algorithms = SimpleNamespace(RSAAlgorithm=_RSAAlgorithm)
    module.decode = lambda *args, **kwargs: {"serviceUrl": service_url_claim}
    return module


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        if url.endswith("openidconfiguration"):
            return _FakeResponse({"jwks_uri": "https://login.botframework.com/keys"})
        return _FakeResponse({
            "keys": [{
                "kid": "kid-1",
                "kty": "RSA",
                "n": "abc",
                "e": "AQAB",
                "endorsements": ["msteams"],
            }]
        })


@pytest.mark.asyncio
async def test_authenticator_accepts_valid_hmac():
    secret_b64 = base64.b64encode(b"test-webhook-secret").decode()
    validator = TeamsAuthValidator(
        client_id="bot-id",
        webhook_secret=secret_b64,
    )
    body = b'{"text":"hello"}'
    auth = _hmac_auth_header(body, secret_b64)

    assert await validator.authenticate(body, auth) is True


@pytest.mark.asyncio
async def test_authenticator_rejects_hmac_without_secret():
    secret_b64 = base64.b64encode(b"test-webhook-secret").decode()
    validator = TeamsAuthValidator(
        client_id="bot-id",
        webhook_secret="",
    )
    body = b'{"text":"hello"}'
    auth = _hmac_auth_header(body, secret_b64)

    assert await validator.authenticate(body, auth) is False


@pytest.mark.asyncio
async def test_authenticator_accepts_valid_bearer_token():
    validator = TeamsAuthValidator(
        client_id="bot-app-id",
        webhook_secret="",
    )
    body = json.dumps({
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "channelId": "msteams",
        "conversation": {"id": "conv-1"},
        "text": "hello",
    }).encode()
    fake_jwt = _fake_jwt_module(
        service_url_claim="https://smba.trafficmanager.net/amer/",
    )

    with patch.dict(sys.modules, {"jwt": fake_jwt}), patch(
        "yigthinker.channels.teams.auth.httpx.AsyncClient",
        _FakeAsyncClient,
    ):
        assert await validator.authenticate(body, "Bearer fake.jwt.token") is True


@pytest.mark.asyncio
async def test_authenticator_rejects_bearer_when_service_url_mismatches():
    validator = TeamsAuthValidator(
        client_id="bot-app-id",
        webhook_secret="",
    )
    body = json.dumps({
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "channelId": "msteams",
    }).encode()
    fake_jwt = _fake_jwt_module(
        service_url_claim="https://smba.trafficmanager.net/emea/",
    )

    with patch.dict(sys.modules, {"jwt": fake_jwt}), patch(
        "yigthinker.channels.teams.auth.httpx.AsyncClient",
        _FakeAsyncClient,
    ):
        assert await validator.authenticate(body, "Bearer fake.jwt.token") is False


@pytest.mark.asyncio
async def test_authenticator_rejects_bearer_when_key_not_endorsed():
    validator = TeamsAuthValidator(
        client_id="bot-app-id",
        webhook_secret="",
    )
    body = json.dumps({
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "channelId": "msteams",
    }).encode()
    fake_jwt = _fake_jwt_module(
        service_url_claim="https://smba.trafficmanager.net/amer/",
    )

    class _UnendorsedClient(_FakeAsyncClient):
        async def get(self, url: str):
            if url.endswith("openidconfiguration"):
                return _FakeResponse({"jwks_uri": "https://login.botframework.com/keys"})
            return _FakeResponse({
                "keys": [{
                    "kid": "kid-1",
                    "kty": "RSA",
                    "n": "abc",
                    "e": "AQAB",
                    "endorsements": ["webchat"],
                }]
            })

    with patch.dict(sys.modules, {"jwt": fake_jwt}), patch(
        "yigthinker.channels.teams.auth.httpx.AsyncClient",
        _UnendorsedClient,
    ):
        assert await validator.authenticate(body, "Bearer fake.jwt.token") is False
