"""Shared-kernel re-export of SessionContext and QuotedMessage for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definitions
live in yigthinker.session; this module is a stable public surface.
"""
from __future__ import annotations

from yigthinker.session import QuotedMessage, SessionContext

__all__ = ["SessionContext", "QuotedMessage"]
