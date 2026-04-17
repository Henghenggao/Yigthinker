"""Shared-kernel re-export of WorkflowRegistry for presence/ consumers.

Presence-layer code (channels, cli, tui, gateway) imports from
yigthinker.core.* to keep the import graph clean. The actual definition
lives in yigthinker.tools.workflow.registry; this module is a stable public
surface.
"""
from __future__ import annotations

from yigthinker.tools.workflow.registry import WorkflowRegistry

__all__ = ["WorkflowRegistry"]
