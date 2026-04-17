"""Shared-kernel re-export of AgentLoop for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definition
lives in yigthinker.agent; this module is a stable public surface.
"""
from __future__ import annotations

from yigthinker.agent import AgentLoop

__all__ = ["AgentLoop"]
