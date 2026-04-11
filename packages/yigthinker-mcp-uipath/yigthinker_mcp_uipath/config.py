"""Load UiPath configuration from environment variables.

Variable names are flat underscore-only per CONTEXT.md D-10 so that
``yigthinker/mcp/loader.py``'s ``_resolve_env`` can route ``vault://`` lookups.

The 6 env vars map 1:1 to the 6 fields ``UipathAuth`` + ``OrchestratorClient``
need (D-09 + D-13):

    UIPATH_CLIENT_ID      -> client_id     (UipathAuth)
    UIPATH_CLIENT_SECRET  -> client_secret (UipathAuth)
    UIPATH_TENANT         -> tenant_name   (UipathAuth)
    UIPATH_ORGANIZATION   -> organization  (UipathAuth)
    UIPATH_SCOPE          -> scope         (UipathAuth, space-separated string)
    UIPATH_BASE_URL       -> base_url      (OrchestratorClient)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_SCOPE = "OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring"


@dataclass(frozen=True)
class UipathConfig:
    """Immutable bundle of UiPath configuration loaded from the environment.

    Field names mirror the 6 env vars read by :meth:`from_env`. All fields are
    required at runtime, but ``scope`` falls back to :data:`DEFAULT_SCOPE` when
    ``UIPATH_SCOPE`` is unset.
    """

    client_id: str
    client_secret: str
    tenant_name: str              # D-09
    organization: str             # D-09
    scope: str                    # D-09 — space-separated string, NOT list
    base_url: str                 # e.g. "https://cloud.uipath.com/acmecorp/DefaultTenant/orchestrator_"

    @classmethod
    def from_env(cls) -> "UipathConfig":
        """Build a :class:`UipathConfig` from ``os.environ``.

        Raises :class:`RuntimeError` with a human-readable message listing any
        missing required variables. ``UIPATH_SCOPE`` is optional and falls back
        to :data:`DEFAULT_SCOPE`.
        """
        required = (
            "UIPATH_CLIENT_ID",
            "UIPATH_CLIENT_SECRET",
            "UIPATH_BASE_URL",
            "UIPATH_TENANT",
            "UIPATH_ORGANIZATION",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "yigthinker-mcp-uipath: missing required env vars: "
                f"{', '.join(missing)}. "
                "Set UIPATH_CLIENT_ID, UIPATH_CLIENT_SECRET, UIPATH_BASE_URL, "
                "UIPATH_TENANT, UIPATH_ORGANIZATION. "
                "See README Configuration section for the vault:// mapping via .mcp.json."
            )
        # UIPATH_SCOPE is optional — falls back to the 5-scope default. Per
        # RFC 6749 (Pitfall 3) the value is space-separated, NOT comma.
        scope = os.environ.get("UIPATH_SCOPE", DEFAULT_SCOPE).strip()
        return cls(
            client_id=os.environ["UIPATH_CLIENT_ID"],
            client_secret=os.environ["UIPATH_CLIENT_SECRET"],
            tenant_name=os.environ["UIPATH_TENANT"],
            organization=os.environ["UIPATH_ORGANIZATION"],
            scope=scope,
            base_url=os.environ["UIPATH_BASE_URL"].rstrip("/"),
        )


def load_config() -> UipathConfig:
    """Thin wrapper around :meth:`UipathConfig.from_env` for callers that prefer
    a module-level function (per PLAN 11-06 ``artifacts.contains = 'load_config'``).
    """
    return UipathConfig.from_env()


__all__ = ["UipathConfig", "DEFAULT_SCOPE", "load_config"]
