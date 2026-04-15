"""Abstract channel adapter protocol for enterprise messaging platforms."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from yigthinker.gateway.server import GatewayServer
    from yigthinker.session import QuotedMessage


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
