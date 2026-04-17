"""Shared-kernel re-export of build_app for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definition
lives in yigthinker.builder; this module is a stable public surface.
"""
from __future__ import annotations

from yigthinker.builder import build_app

__all__ = ["build_app"]
