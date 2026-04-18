"""Teams adapter must emit a public HTTPS base URL for outbound asset URLs.

2026-04-18 UAT finding: `_gateway_base_url()` fell back to
``http://127.0.0.1:8766`` when no public URL was configured. Chart images
and signed-URL download endpoints embed this base URL in Adaptive Cards;
Teams' backend cannot reach loopback or HTTP (non-TLS) URLs, so the image
silently doesn't render and download buttons go dead.

Contract (post-2026-04-18-evening correction):

1. If ``settings["gateway"]["public_base_url"]`` is set, use it.
2. Else fall back to the loopback with a structured warning logged once
   (so an ops-level misconfiguration is discoverable).

**Explicitly NOT derived** from ``channels.teams.service_url`` — that
setting is the *outbound* Bot Framework service URL (where we POST
replies). An earlier fix (same day) tried to reuse it as the public asset
URL, which broke every outbound reply with 404s because the bot framework
service isn't the same origin as our gateway. These two URLs are
orthogonal and must be configured separately.
"""
from __future__ import annotations

import logging

import pytest


def _make_adapter(settings: dict, gateway_settings: dict | None = None):
    """Build a TeamsAdapter with a minimal fake gateway."""
    from types import SimpleNamespace
    from yigthinker.presence.channels.teams.adapter import TeamsAdapter

    teams_cfg = settings.get("channels", {}).get("teams", {})
    adapter = TeamsAdapter(teams_cfg)
    # _gateway_base_url reads from self._gateway._settings
    fake_gw = SimpleNamespace(_settings=settings)
    adapter._gateway = fake_gw
    return adapter


def test_base_url_prefers_public_base_url_setting():
    """Explicit gateway.public_base_url beats everything."""
    adapter = _make_adapter({
        "gateway": {
            "public_base_url": "https://74v11r1x-8766.uks1.devtunnels.ms",
            "host": "127.0.0.1",
            "port": 8766,
        },
        "channels": {"teams": {}},
    })
    assert adapter._gateway_base_url() == "https://74v11r1x-8766.uks1.devtunnels.ms"


def test_base_url_strips_trailing_slash_from_public_base_url():
    adapter = _make_adapter({
        "gateway": {"public_base_url": "https://example.com/"},
        "channels": {"teams": {}},
    })
    assert adapter._gateway_base_url() == "https://example.com"


def test_base_url_ignores_teams_service_url_entirely():
    """channels.teams.service_url is the OUTBOUND Bot Framework service URL
    (where replies go — typically smba.trafficmanager.net). It must NOT be
    reused as the public asset URL for this adapter's outbound image
    links; conflating the two broke every reply with 404s in an earlier
    fix attempt (same-day revert, 2026-04-18 evening)."""
    adapter = _make_adapter({
        "gateway": {"host": "127.0.0.1", "port": 8766},
        "channels": {
            "teams": {
                # Even a public HTTPS value here must NOT influence
                # _gateway_base_url — it's a different URL semantically.
                "service_url": "https://74v11r1x-8766.uks1.devtunnels.ms/webhook/teams",
            }
        },
    })
    url = adapter._gateway_base_url()
    # Must fall through to loopback because no gateway.public_base_url is set.
    assert url == "http://127.0.0.1:8766"


def test_base_url_final_fallback_to_loopback(caplog):
    """When no public URL is discoverable, fall back to the bind host:port.
    Emit a warning once so ops can diagnose why images aren't rendering."""
    caplog.set_level(logging.WARNING, logger="yigthinker.presence.channels.teams.adapter")
    adapter = _make_adapter({
        "gateway": {"host": "127.0.0.1", "port": 8766},
        "channels": {"teams": {}},
    })
    url = adapter._gateway_base_url()
    assert url == "http://127.0.0.1:8766"
    # At least one record mentions that Teams cannot reach loopback
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "teams" in joined.lower() or "loopback" in joined.lower() or "public" in joined.lower()


def test_base_url_maps_empty_host_to_localhost():
    """Existing behavior: 0.0.0.0 / empty host → 127.0.0.1. Don't regress."""
    adapter = _make_adapter({
        "gateway": {"host": "0.0.0.0", "port": 8766},
        "channels": {"teams": {}},
    })
    assert adapter._gateway_base_url() == "http://127.0.0.1:8766"


# ---------------------------------------------------------------------------
# Integration: _is_public_base_url recognises the new HTTPS paths
# ---------------------------------------------------------------------------

def test_is_public_base_url_accepts_devtunnel_https():
    adapter = _make_adapter({
        "gateway": {"public_base_url": "https://74v11r1x-8766.uks1.devtunnels.ms"},
        "channels": {"teams": {}},
    })
    assert adapter._is_public_base_url("https://74v11r1x-8766.uks1.devtunnels.ms") is True


def test_is_public_base_url_rejects_loopback():
    adapter = _make_adapter({"gateway": {}, "channels": {"teams": {}}})
    assert adapter._is_public_base_url("http://127.0.0.1:8766") is False
    assert adapter._is_public_base_url("http://localhost:8766") is False
