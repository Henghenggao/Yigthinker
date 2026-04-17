"""Tests for Teams outbound file delivery via signed-URL (quick-260416-kyn Task 3).

Covers:
- render_file_saved with/without download_url
- _build_card_for_artifact wiring for xlsx/pdf artifacts → Action.OpenUrl
- Fallback when public_base_url is missing / store unavailable / issue raises
- _is_deliverable matrix (binary suffixes/mimes vs text-only artifacts)
- _is_public_base_url heuristic
- CJK / `+` URL-encoding in filenames
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from yigthinker.presence.channels.teams.adapter import TeamsAdapter
from yigthinker.presence.channels.teams.cards import TeamsCardRenderer


# ── Fixtures / helpers ───────────────────────────────────────────────────


def _make_adapter(
    public_base_url: str | None = None,
    token_store: object | None = None,
) -> TeamsAdapter:
    gw_cfg: dict[str, object] = {}
    if public_base_url is not None:
        gw_cfg["public_base_url"] = public_base_url
    gateway = SimpleNamespace(
        _settings={"gateway": gw_cfg},
        _file_token_store=token_store,
    )
    adapter = TeamsAdapter(
        config={
            "tenant_id": "t",
            "client_id": "c",
            "client_secret": "s",
            "webhook_secret": "w",
        },
    )
    adapter._gateway = gateway  # type: ignore[assignment]
    return adapter


class _FakeStore:
    """Records issue() calls and returns a deterministic token."""

    def __init__(self, token: str = "TOK123", raise_on_issue: bool = False):
        self.token = token
        self.raise_on_issue = raise_on_issue
        self.issued: list[Path] = []

    def issue(self, path: Path) -> str:
        if self.raise_on_issue:
            raise RuntimeError("issue failed")
        self.issued.append(path)
        return self.token


# ── Card renderer — render_file_saved with download_url ──────────────────


def test_render_file_saved_without_url_has_no_actions_key():
    """Regression guard for quick-260416-j3y: when no download_url, the card
    must remain card-only (no actions key)."""
    renderer = TeamsCardRenderer()
    card = renderer.render_file_saved("build_pl.py", 4321, summary="Script")
    assert "actions" not in card


def test_render_file_saved_with_url_emits_openurl_action():
    renderer = TeamsCardRenderer()
    url = "https://example.ngrok.app/api/files/abc123?name=x.xlsx"
    card = renderer.render_file_saved(
        "report.xlsx", 10_000, summary="Q3 P&L", download_url=url,
    )
    assert card["actions"] == [
        {
            "type": "Action.OpenUrl",
            "title": "Download report.xlsx",
            "url": url,
        }
    ]
    # Summary still rendered
    bodies = [b.get("text") for b in card["body"] if b.get("type") == "TextBlock"]
    assert "Q3 P&L" in bodies


# ── _is_deliverable matrix ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,mime,expected",
    [
        ("/x/report.xlsx", "", True),
        ("/x/legacy.xls", "", True),
        ("/x/data.csv", "", True),
        ("/x/report.pdf", "", True),
        ("/x/doc.docx", "", True),
        ("/x/chart.png", "", True),
        ("/x/script.py", "", False),
        ("/x/notes.md", "", False),
        ("/x/readme.txt", "", False),
        ("/x/query.sql", "", False),
        (
            "/x/noext",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            True,
        ),
        ("/x/noext", "application/pdf", True),
        ("/x/noext", "text/plain", False),
        ("", "", False),
    ],
)
def test_is_deliverable_matrix(path, mime, expected):
    adapter = _make_adapter()
    assert adapter._is_deliverable(path, mime) is expected


# ── _is_public_base_url heuristic ────────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected",
    [
        ("", False),
        ("http://127.0.0.1:8766", False),
        ("http://localhost:8766", False),
        ("http://0.0.0.0:8766", False),
        ("https://example.ngrok.app", True),
        ("https://bot.mycompany.com", True),
        ("http://10.0.0.5:8080", True),  # LAN IP is "public enough" — bot controls this
    ],
)
def test_is_public_base_url(url, expected):
    adapter = _make_adapter()
    assert adapter._is_public_base_url(url) is expected


# ── _build_card_for_artifact integration ─────────────────────────────────


def test_xlsx_artifact_issues_signed_url_when_public_base_url_set(tmp_path):
    store = _FakeStore(token="TOK123")
    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app",
        token_store=store,
    )

    f = tmp_path / "FCST_2+10 10_P&L.xlsx"
    f.write_bytes(b"x")

    artifact = {
        "kind": "file",
        "filename": "FCST_2+10 10_P&L.xlsx",
        "path": str(f),
        "bytes": 1,
        "summary": "Added P&L sheet",
        "mime_type": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    }
    card = adapter._build_card_for_artifact("done", artifact)

    # Adapter called issue with resolved path
    assert len(store.issued) == 1
    assert store.issued[0] == f.resolve()

    # Card has an OpenUrl action with properly URL-quoted filename
    assert "actions" in card
    action = card["actions"][0]
    assert action["type"] == "Action.OpenUrl"
    # urllib.parse.quote: `+` → %2B, space → %20, `&` → %26
    assert (
        "FCST_2%2B10%2010_P%26L.xlsx" in action["url"]
    )
    assert action["url"].startswith("https://example.ngrok.app/api/files/TOK123")


def test_xlsx_artifact_falls_back_when_base_url_missing(tmp_path):
    store = _FakeStore()
    adapter = _make_adapter(public_base_url="", token_store=store)

    f = tmp_path / "out.xlsx"
    f.write_bytes(b"x")
    artifact = {
        "kind": "file", "filename": "out.xlsx", "path": str(f),
        "bytes": 1, "summary": None, "mime_type": "",
    }
    card = adapter._build_card_for_artifact("done", artifact)
    # No Action.OpenUrl when base URL is loopback fallback
    assert "actions" not in card
    assert store.issued == []


def test_xlsx_artifact_falls_back_when_store_missing(tmp_path):
    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app", token_store=None,
    )
    f = tmp_path / "out.xlsx"
    f.write_bytes(b"x")
    artifact = {
        "kind": "file", "filename": "out.xlsx", "path": str(f),
        "bytes": 1, "summary": None, "mime_type": "",
    }
    card = adapter._build_card_for_artifact("done", artifact)
    assert "actions" not in card


def test_xlsx_artifact_falls_back_when_issue_raises(tmp_path):
    store = _FakeStore(raise_on_issue=True)
    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app", token_store=store,
    )
    f = tmp_path / "out.xlsx"
    f.write_bytes(b"x")
    artifact = {
        "kind": "file", "filename": "out.xlsx", "path": str(f),
        "bytes": 1, "summary": None, "mime_type": "",
    }
    # Must NOT raise — falls back to card-only.
    card = adapter._build_card_for_artifact("done", artifact)
    assert "actions" not in card


def test_text_artifact_does_NOT_issue_token(tmp_path):
    """artifact_write outputs (.py/.md/.sql) must stay card-only."""
    store = _FakeStore()
    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app", token_store=store,
    )
    f = tmp_path / "build_pl.py"
    f.write_text("print('hi')")
    artifact = {
        "kind": "file", "filename": "build_pl.py", "path": str(f),
        "bytes": 11, "summary": "Build script", "mime_type": "",
    }
    card = adapter._build_card_for_artifact("done", artifact)
    assert "actions" not in card
    assert store.issued == []


def test_cjk_filename_survives_url_quote(tmp_path):
    store = _FakeStore(token="TOK")
    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app", token_store=store,
    )
    f = tmp_path / "zai.xlsx"
    f.write_bytes(b"x")
    artifact = {
        "kind": "file",
        "filename": "在这个.xlsx",
        "path": str(f),
        "bytes": 1,
        "summary": None,
        "mime_type": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    }
    card = adapter._build_card_for_artifact("", artifact)
    action = card["actions"][0]
    # No raw CJK bytes in the URL — they must be %-encoded via
    # urllib.parse.quote (UTF-8 → %E5%9C%A8 etc.)
    assert "%E5%9C%A8" in action["url"]
    # No raw `/` path-separator escapes: quote(...) preserves `/` by
    # default but our filename has none so the URL should be clean.
    assert "在这个" not in action["url"]


def test_build_card_for_artifact_chart_still_works(tmp_path, monkeypatch):
    """Regression: chart artifacts must not regress through the file branch."""
    # Redirect CHART_CACHE_DIR to tmp_path so we don't pollute the real cache.
    import yigthinker.presence.gateway.server as server_mod
    monkeypatch.setattr(server_mod, "CHART_CACHE_DIR", tmp_path / "charts")

    adapter = _make_adapter(
        public_base_url="https://example.ngrok.app",
        token_store=_FakeStore(),
    )
    artifact = {
        "kind": "chart",
        "chart_name": "Revenue",
        "chart_json": "{\"data\":[],\"layout\":{}}",
    }
    # _build_chart_card attempts a PNG export which typically fails
    # without kaleido — the adapter already handles that fallback path.
    card = adapter._build_card_for_artifact("see chart", artifact)
    assert isinstance(card, dict)
    assert card.get("type") == "AdaptiveCard"
