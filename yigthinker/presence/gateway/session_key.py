"""Session key derivation for multi-channel, multi-user session scoping."""
from __future__ import annotations

import re

_VALID_SEGMENT = re.compile(r"^[\w\-.]+$")


class SessionKey:
    """Static methods for constructing and parsing session keys.

    Four scoping modes:
      - per-sender:  {channel}:{sender_id}      — one workspace per user (default)
      - per-channel: {channel}:chat:{chat_id}    — shared workspace for group chat
      - named:       {channel}:{sender_id}:{lbl} — user-created named project
      - global:      global                      — single shared session
    """

    @staticmethod
    def per_sender(channel: str, sender_id: str) -> str:
        _validate(channel, sender_id)
        return f"{channel}:{sender_id}"

    @staticmethod
    def per_channel(channel: str, chat_id: str) -> str:
        _validate(channel, chat_id)
        return f"{channel}:chat:{chat_id}"

    @staticmethod
    def named(channel: str, sender_id: str, label: str) -> str:
        _validate(channel, sender_id, label)
        return f"{channel}:{sender_id}:{label}"

    @staticmethod
    def global_key() -> str:
        return "global"

    @staticmethod
    def parse(key: str) -> dict[str, str]:
        """Parse a session key into its component parts.

        Returns dict with keys: scope, channel, sender_id, chat_id, label
        (missing parts are empty strings).
        """
        if key == "global":
            return {"scope": "global", "channel": "", "sender_id": "", "chat_id": "", "label": ""}

        parts = key.split(":")
        if len(parts) == 3 and parts[1] == "chat":
            return {"scope": "per-channel", "channel": parts[0], "sender_id": "", "chat_id": parts[2], "label": ""}
        if len(parts) == 3:
            return {"scope": "named", "channel": parts[0], "sender_id": parts[1], "chat_id": "", "label": parts[2]}
        if len(parts) == 2:
            return {"scope": "per-sender", "channel": parts[0], "sender_id": parts[1], "chat_id": "", "label": ""}

        raise ValueError(f"Cannot parse session key: {key!r}")

    @staticmethod
    def from_config(scope: str, channel: str, sender_id: str = "",
                    chat_id: str = "", label: str = "") -> str:
        """Build a session key from scope config and identifiers."""
        if scope == "global":
            return SessionKey.global_key()
        if scope == "per-channel" and chat_id:
            return SessionKey.per_channel(channel, chat_id)
        if scope == "named" and label:
            return SessionKey.named(channel, sender_id, label)
        return SessionKey.per_sender(channel, sender_id)


def _validate(*segments: str) -> None:
    for seg in segments:
        if not seg or not _VALID_SEGMENT.match(seg):
            raise ValueError(f"Invalid session key segment: {seg!r}")
