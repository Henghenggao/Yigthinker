"""Shared-kernel re-export of LLMProvider for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definition
lives in yigthinker.providers.base; this module is a stable public surface.
"""
from __future__ import annotations

from yigthinker.providers.base import LLMProvider

__all__ = ["LLMProvider"]
