from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass
class SubagentInfo:
    subagent_id: str
    name: str
    status: Literal["running", "completed", "failed", "cancelled"]
    started_at: float
    task: asyncio.Task | None = None
    final_text: str = ""


class SubagentManager:
    """Per-session subagent lifecycle manager."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._subagents: dict[str, SubagentInfo] = {}
        self._max_concurrent = max_concurrent
        self._pending_notifications: list[str] = []

    @property
    def running_count(self) -> int:
        return sum(1 for s in self._subagents.values() if s.status == "running")

    def can_spawn(self) -> bool:
        return self.running_count < self._max_concurrent

    def register(self, name: str, task: asyncio.Task | None = None) -> SubagentInfo:
        subagent_id = str(uuid.uuid4())
        info = SubagentInfo(
            subagent_id=subagent_id,
            name=name,
            status="running",
            started_at=time.monotonic(),
            task=task,
        )
        self._subagents[subagent_id] = info
        return info

    def complete(self, subagent_id: str, final_text: str) -> None:
        info = self._subagents.get(subagent_id)
        if info:
            info.status = "completed"
            info.final_text = final_text

    def fail(self, subagent_id: str, error: str) -> None:
        info = self._subagents.get(subagent_id)
        if info:
            info.status = "failed"
            info.final_text = error

    def list_all(self) -> list[SubagentInfo]:
        return list(self._subagents.values())

    def get(self, subagent_id: str) -> SubagentInfo | None:
        return self._subagents.get(subagent_id)

    def cancel(self, subagent_id: str) -> bool:
        info = self._subagents.get(subagent_id)
        if info and info.task and info.status == "running":
            info.task.cancel()
            info.status = "cancelled"
            return True
        return False

    def add_notification(self, message: str) -> None:
        self._pending_notifications.append(message)

    def drain_notifications(self) -> list[str]:
        notifications = list(self._pending_notifications)
        self._pending_notifications.clear()
        return notifications

    async def shutdown(self) -> None:
        for info in self._subagents.values():
            if info.status == "running" and info.task:
                info.task.cancel()
                info.status = "cancelled"
