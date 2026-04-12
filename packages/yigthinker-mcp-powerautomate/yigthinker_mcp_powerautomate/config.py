"""Load Power Automate configuration from environment variables.

Variable names are flat underscore-only per CONTEXT.md D-10/D-11 so that
``yigthinker/mcp/loader.py``'s ``_resolve_env`` can route ``vault://`` lookups.

The 6 env vars map to the fields ``PowerAutomateAuth`` + ``PowerAutomateClient``
need:

    POWERAUTOMATE_TENANT_ID     -> tenant_id     (PowerAutomateAuth)
    POWERAUTOMATE_CLIENT_ID     -> client_id     (PowerAutomateAuth)
    POWERAUTOMATE_CLIENT_SECRET -> client_secret (PowerAutomateAuth)
    POWERAUTOMATE_SCOPE         -> scope         (PowerAutomateAuth, optional)
    POWERAUTOMATE_AUTHORITY     -> authority      (PowerAutomateAuth, optional)
    POWERAUTOMATE_BASE_URL      -> base_url      (PowerAutomateClient, optional)
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SCOPE = "https://service.flow.microsoft.com//.default"
DEFAULT_BASE_URL = "https://api.flow.microsoft.com"
DEFAULT_AUTHORITY_TPL = "https://login.microsoftonline.com/{tenant_id}"


@dataclass(frozen=True)
class PowerAutomateConfig:
    """Immutable bundle of Power Automate configuration loaded from the environment.

    Three fields are required (tenant_id, client_id, client_secret). The
    remaining three fall back to sensible defaults when their env vars are unset.
    """

    tenant_id: str
    client_id: str
    client_secret: str
    scope: str = DEFAULT_SCOPE
    base_url: str = DEFAULT_BASE_URL
    authority: str = ""  # computed from tenant_id if empty

    @classmethod
    def from_env(cls) -> "PowerAutomateConfig":
        """Build a :class:`PowerAutomateConfig` from ``os.environ``.

        Raises :class:`RuntimeError` with a human-readable message listing any
        missing required variables. Optional vars fall back to defaults.
        """
        raise NotImplementedError("Plan 12-06 replaces this")


def load_config() -> PowerAutomateConfig:
    """Thin wrapper around :meth:`PowerAutomateConfig.from_env`."""
    return PowerAutomateConfig.from_env()


__all__ = ["PowerAutomateConfig", "DEFAULT_SCOPE", "DEFAULT_BASE_URL",
           "DEFAULT_AUTHORITY_TPL", "load_config"]
