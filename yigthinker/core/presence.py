"""Channel adapter Protocol — moved from presence/channels/base.py in Phase 1b.

Phase 1b adds a required ``deliver_artifact`` method; artifact delivery is now
a first-class concern on the Protocol instead of an ad-hoc helper.

``Artifact`` is a structured dict — see ``yigthinker.presence.channels.artifacts``
for the schema (chart artifacts carry ``{kind, chart_name, chart_json}``; file
artifacts carry ``{kind: "file", filename, path, bytes, summary, mime_type}``).
We use a ``TypeAlias`` rather than a dataclass to preserve the existing runtime
shape and avoid forcing a migration not required by Phase 1b.

Only channel-type presences (Teams / Feishu / GChat) implement this Protocol.
CLI, TUI, and Gateway live in ``presence/`` but are not ChannelAdapters.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, runtime_checkable

if TYPE_CHECKING:
    from yigthinker.presence.gateway.server import GatewayServer
    from yigthinker.session import QuotedMessage


Artifact: TypeAlias = dict[str, Any]


@runtime_checkable
class ChannelAdapter(Protocol):
    """Interface for messaging platform adapters (Feishu, Teams, Google Chat).

    Each adapter:
      1. Registers webhook endpoints on the gateway's FastAPI app
      2. Derives a session key from the platform event (sender, chat, etc.)
      3. Routes messages through ``gateway.handle_message()``
      4. Sends results back in the platform's native card/message format
    """

    name: str

    async def start(self, gateway: GatewayServer) -> None:
        """Register webhook routes and start receiving messages."""
        ...

    async def stop(self) -> None:
        """Graceful shutdown — clean up connections and background tasks."""
        ...

    def session_key(self, event: dict[str, Any]) -> str:
        """Derive a session key from a platform event."""
        ...

    async def send_response(
        self,
        event: dict[str, Any],
        text: str,
        vars_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        """Send a formatted response back to the platform."""
        ...

    async def extract_quoted_messages(self, event: dict[str, Any]) -> list[QuotedMessage]:
        """Extract referenced/quoted messages from a platform event.

        Returns original message text for context emphasis.
        Default: empty list (no quote support).
        """
        ...

    async def deliver_artifact(
        self,
        event: dict[str, Any],
        artifact: Artifact,
    ) -> None:
        """Deliver a file/chart/report artifact to the user.

        Phase 1b: REQUIRED method. Adapters that cannot render a given artifact
        kind should fall back to posting the artifact's path/URL as text via
        :meth:`send_response`.
        """
        ...
