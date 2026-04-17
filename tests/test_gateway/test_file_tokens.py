"""Tests for the FileTokenStore (quick-260416-kyn Task 2).

Covers issue/resolve round-trip, HMAC tamper detection, TTL expiry, thread
safety, absolute-path enforcement, and the ``/api/files/{token}`` route wired
onto ``GatewayServer``. The route tests use FastAPI TestClient against a
minimally-constructed server (no ``start()`` — we want a cheap synchronous
harness).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yigthinker.presence.gateway.file_tokens import (
    DEFAULT_FILE_TOKEN_TTL_SECONDS,
    FileTokenStore,
)


# ── FileTokenStore ───────────────────────────────────────────────────────


def test_issue_then_resolve_roundtrip(tmp_path):
    store = FileTokenStore(secret=b"supersecret", ttl_seconds=60)
    f = tmp_path / "out.xlsx"
    f.write_bytes(b"fake xlsx bytes")

    token = store.issue(f.resolve())
    assert isinstance(token, str) and token
    resolved = store.resolve(token)
    assert resolved is not None
    assert resolved == f.resolve()


def test_issue_rejects_nonabsolute_path(tmp_path, monkeypatch):
    store = FileTokenStore(secret=b"k", ttl_seconds=60)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        store.issue(Path("relative/x.xlsx"))


def test_resolve_unknown_token_returns_none():
    store = FileTokenStore(secret=b"k", ttl_seconds=60)
    assert store.resolve("garbage") is None
    assert store.resolve("") is None
    assert store.resolve("no.dot") is None


def test_resolve_tampered_token_returns_none(tmp_path):
    store = FileTokenStore(secret=b"k", ttl_seconds=60)
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"x")
    token = store.issue(f.resolve())

    # Flip a character in the signature portion
    nonce, sig = token.split(".", 1)
    tampered = f"{nonce}.{'a' if sig[0] != 'a' else 'b'}{sig[1:]}"
    assert store.resolve(tampered) is None


def test_resolve_expired_returns_none(tmp_path, monkeypatch):
    """After TTL elapses, resolve returns None and drops the entry."""
    current = [1000.0]

    def fake_monotonic():
        return current[0]

    monkeypatch.setattr(
        "yigthinker.presence.gateway.file_tokens.time.monotonic", fake_monotonic
    )

    store = FileTokenStore(secret=b"k", ttl_seconds=30)
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"x")
    token = store.issue(f.resolve())

    # Within TTL
    assert store.resolve(token) == f.resolve()

    # Advance past TTL
    current[0] = 1000.0 + 31.0
    assert store.resolve(token) is None


def test_issued_tokens_distinct_for_same_path(tmp_path):
    """Each issue() call must produce a fresh nonce → distinct token."""
    store = FileTokenStore(secret=b"k", ttl_seconds=60)
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"x")
    t1 = store.issue(f.resolve())
    t2 = store.issue(f.resolve())
    assert t1 != t2
    assert store.resolve(t1) == f.resolve()
    assert store.resolve(t2) == f.resolve()


def test_thread_safety_smoke(tmp_path):
    """Concurrent issue() from many threads produces distinct resolvable tokens."""
    store = FileTokenStore(secret=b"k", ttl_seconds=60)
    files = []
    for i in range(20):
        f = tmp_path / f"x{i}.xlsx"
        f.write_bytes(b"x")
        files.append(f.resolve())

    tokens: list[str] = []
    lock = threading.Lock()

    def _issue(p):
        tok = store.issue(p)
        with lock:
            tokens.append(tok)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_issue, files))

    assert len(tokens) == len(files)
    assert len(set(tokens)) == len(tokens)
    # All resolve back to their original path
    for tok in tokens:
        assert store.resolve(tok) is not None


def test_default_ttl_constant_is_30_minutes():
    """DEFAULT_FILE_TOKEN_TTL_SECONDS is 30 minutes per RESEARCH.md."""
    assert DEFAULT_FILE_TOKEN_TTL_SECONDS == 1800


# ── /api/files/{token} route ──────────────────────────────────────────────


@pytest.fixture
def gateway_client(tmp_path, monkeypatch):
    """Build a minimal GatewayServer bound to tmp_path for artifacts.

    We monkeypatch Path.home in the cleanup module so that ARTIFACTS_ROOT
    falls under tmp_path (unused by the route tests directly, but keeps the
    server init side-effect-free against the real user home).
    """
    import yigthinker.presence.gateway.artifacts_cleanup as cleanup_mod
    monkeypatch.setattr(cleanup_mod.Path, "home", classmethod(lambda cls: tmp_path))

    from yigthinker.presence.gateway.server import GatewayServer

    settings = {
        "gateway": {
            "host": "127.0.0.1",
            "port": 0,
            "file_token_secret": "testsecret" * 4,  # non-empty so no autogen
            "file_token_ttl_seconds": 60,
            "artifact_ttl_seconds": 7 * 24 * 3600,
        },
        "channels": {},
    }
    server = GatewayServer(settings)
    client = TestClient(server.app)
    return server, client


def test_route_serves_file_for_valid_token(tmp_path, gateway_client):
    server, client = gateway_client
    f = tmp_path / "report.xlsx"
    f.write_bytes(b"PK\x03\x04" + b"fake xlsx body" * 32)

    token = server._file_token_store.issue(f.resolve())

    resp = client.get(f"/api/files/{token}", params={"name": "report.xlsx"})
    assert resp.status_code == 200
    # Either mime_type or content-type header should carry the xlsx type
    assert "spreadsheetml" in resp.headers.get("content-type", "")
    # Content-Disposition should reference the filename
    disp = resp.headers.get("content-disposition", "")
    assert "report.xlsx" in disp
    # Body matches
    assert resp.content == f.read_bytes()


def test_route_returns_404_for_bad_token(gateway_client):
    _, client = gateway_client
    resp = client.get("/api/files/garbage.token")
    assert resp.status_code == 404


def test_route_returns_404_when_file_missing(tmp_path, gateway_client):
    server, client = gateway_client
    f = tmp_path / "ghost.xlsx"
    f.write_bytes(b"x")
    token = server._file_token_store.issue(f.resolve())
    f.unlink()  # delete before the client fetches

    resp = client.get(f"/api/files/{token}")
    assert resp.status_code == 404


def test_route_defaults_filename_to_path_basename(tmp_path, gateway_client):
    server, client = gateway_client
    f = tmp_path / "default_name.xlsx"
    f.write_bytes(b"x")
    token = server._file_token_store.issue(f.resolve())
    resp = client.get(f"/api/files/{token}")  # no ?name=
    assert resp.status_code == 200
    assert "default_name.xlsx" in resp.headers.get("content-disposition", "")


def test_file_token_secret_autogenerated_when_empty(tmp_path, monkeypatch):
    """When settings.gateway.file_token_secret is empty, gateway generates a
    persistent secret under ~/.yigthinker/gateway_file_token.secret."""
    # Redirect Path.home in both gateway modules to tmp_path.
    import yigthinker.presence.gateway.server as server_mod
    import yigthinker.presence.gateway.artifacts_cleanup as cleanup_mod
    monkeypatch.setattr(cleanup_mod.Path, "home", classmethod(lambda cls: tmp_path))
    # server.py uses Path.home() only via the cleanup import / secret write
    # path — patch on the module to be thorough.
    monkeypatch.setattr(server_mod.Path, "home", classmethod(lambda cls: tmp_path))

    from yigthinker.presence.gateway.server import GatewayServer

    settings = {
        "gateway": {
            "host": "127.0.0.1",
            "port": 0,
            "file_token_secret": "",  # empty → autogenerate
        },
    }
    server = GatewayServer(settings)
    assert server._file_token_store is not None
    secret_file = tmp_path / ".yigthinker" / "gateway_file_token.secret"
    assert secret_file.exists()
    assert secret_file.read_text(encoding="utf-8").strip()  # non-empty
