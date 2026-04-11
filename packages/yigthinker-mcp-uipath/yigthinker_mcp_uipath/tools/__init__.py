"""UiPath MCP tool registry (populated by Plan 11-05).

Maps tool name -> ``(input_model, handler)`` tuples. ``server.py``
(Plan 11-06) iterates this at startup to register tools with the low-level
MCP Server.

Per CONTEXT.md D-19 the 5 tools are:

- ``ui_deploy_process`` — build .nupkg, upload, create Release
- ``ui_trigger_job`` — start a job for an existing Release
- ``ui_job_history`` — list recent jobs for a process
- ``ui_manage_trigger`` — create/pause/resume/delete schedules
- ``ui_queue_status`` — return item counts per state for a queue
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .ui_deploy_process import UiDeployProcessInput
from .ui_deploy_process import handle as _deploy
from .ui_job_history import UiJobHistoryInput
from .ui_job_history import handle as _history
from .ui_manage_trigger import UiManageTriggerInput
from .ui_manage_trigger import handle as _manage
from .ui_queue_status import UiQueueStatusInput
from .ui_queue_status import handle as _queue
from .ui_trigger_job import UiTriggerJobInput
from .ui_trigger_job import handle as _trigger

Handler = Callable[[BaseModel, Any], Awaitable[dict]]

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Handler]] = {
    "ui_deploy_process": (UiDeployProcessInput, _deploy),
    "ui_trigger_job": (UiTriggerJobInput, _trigger),
    "ui_job_history": (UiJobHistoryInput, _history),
    "ui_manage_trigger": (UiManageTriggerInput, _manage),
    "ui_queue_status": (UiQueueStatusInput, _queue),
}

__all__ = ["TOOL_REGISTRY"]
