"""Shared-kernel re-export of ConnectionPool for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definition
lives in yigthinker.tools.sql.connection; this module is a stable public surface.
"""
from __future__ import annotations

from yigthinker.tools.sql.connection import ConnectionPool

__all__ = ["ConnectionPool"]
