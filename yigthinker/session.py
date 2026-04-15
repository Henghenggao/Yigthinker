from __future__ import annotations

import asyncio
import copy
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from yigthinker.subagent.manager import SubagentManager

import pandas as pd

from yigthinker.context_manager import ContextManager
from yigthinker.stats import StatsAccumulator
from yigthinker.types import Message


@dataclass
class VarEntry:
    name: str
    value: Any
    var_type: str  # "dataframe", "chart", "artifact", "string"


@dataclass
class VarInfo:
    name: str
    shape: tuple[int, ...]
    dtypes: dict[str, str]
    var_type: str = "dataframe"


@dataclass
class UndoEntry:
    tool_name: str
    original_path: _Path
    backup_path: _Path | None
    created_at: float
    is_new_file: bool


@dataclass
class CheckpointData:
    messages: list[Message]
    vars_snapshot: dict[str, Any]
    created_at: float


class VarRegistry:
    """Session-scoped in-memory store for DataFrames and chart artifacts."""

    def __init__(self) -> None:
        self._vars: dict[str, VarEntry] = {}

    def set(self, name: str, value: Any, var_type: str = "dataframe") -> None:
        self._vars[name] = VarEntry(name=name, value=value, var_type=var_type)

    def get(self, name: str) -> Any:
        if name not in self._vars:
            available = list(self._vars)
            raise KeyError(f"Variable '{name}' not found. Available: {available}")
        return self._vars[name].value

    def list(self) -> list[VarInfo]:
        infos: list[VarInfo] = []
        for name, entry in self._vars.items():
            if isinstance(entry.value, pd.DataFrame):
                infos.append(
                    VarInfo(
                        name=name,
                        shape=entry.value.shape,
                        dtypes={
                            col: str(dtype)
                            for col, dtype in entry.value.dtypes.items()
                        },
                        var_type="dataframe",
                    )
                )
            else:
                infos.append(
                    VarInfo(
                        name=name,
                        shape=(0, 0),
                        dtypes={},
                        var_type=entry.var_type,
                    )
                )
        return infos

    def __contains__(self, name: str) -> bool:
        return name in self._vars


@dataclass
class SessionContext:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    settings: dict[str, Any] = field(default_factory=dict)
    transcript_path: str = ""
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    channel_origin: str = "cli"
    owner_id: str = ""  # identifies the user who owns this session (channel:sender_id)
    vars: VarRegistry = field(default_factory=VarRegistry)
    context_manager: ContextManager = field(default_factory=ContextManager)
    stats: StatsAccumulator = field(default_factory=StatsAccumulator)
    messages: list[Message] = field(default_factory=list)
    undo_stack: list[UndoEntry] = field(default_factory=list)
    subagent_manager: SubagentManager | None = None
    _progress_callback: Callable[[str], None] | None = field(default=None, repr=False)
    _on_tool_event: Callable[[str, dict], None] | None = field(default=None, repr=False)
    _pending_injections: list[str] | None = field(default=None, repr=False)
    _checkpoints: dict[str, CheckpointData] = field(default_factory=dict, repr=False)
    _steering_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)
    _is_running: bool = field(default=False, repr=False)

    async def emit_progress(self, message: str) -> None:
        """Emit a progress message to the UI layer. No-op if no callback set."""
        if self._progress_callback is not None:
            self._progress_callback(message)

    def checkpoint(self, label: str) -> None:
        """Save current state as a named checkpoint.

        Deep-copies all DataFrames so that in-place mutations after
        checkpointing do not corrupt stored state. This is O(n) in DataFrame
        memory — avoid checkpointing sessions with very large DataFrames
        (VarRegistry memory limit enforced separately).
        """
        vars_snapshot: dict[str, Any] = {}
        for info in self.vars.list():
            value = self.vars.get(info.name)
            if isinstance(value, pd.DataFrame):
                vars_snapshot[info.name] = (value.copy(deep=True), info.var_type)
            else:
                vars_snapshot[info.name] = (copy.copy(value), info.var_type)

        self._checkpoints[label] = CheckpointData(
            messages=copy.deepcopy(self.messages),
            vars_snapshot=vars_snapshot,
            created_at=time.time(),
        )

        max_checkpoints = self.settings.get("session", {}).get("max_checkpoints", 10)
        while len(self._checkpoints) > max_checkpoints:
            oldest_key = next(iter(self._checkpoints))
            del self._checkpoints[oldest_key]

    def branch_from(self, label: str) -> "SessionContext":
        """Create a new SessionContext from a named checkpoint.

        Deep-copies DataFrames from the snapshot so the branched context is
        fully independent of both the checkpoint store and the parent context.
        """
        if label not in self._checkpoints:
            raise KeyError(f"Checkpoint '{label}' not found. Available: {list(self._checkpoints)}")
        cp = self._checkpoints[label]
        new_ctx = SessionContext(settings=dict(self.settings))
        new_ctx.messages = copy.deepcopy(cp.messages)
        for name, (value, var_type) in cp.vars_snapshot.items():
            if isinstance(value, pd.DataFrame):
                new_ctx.vars.set(name, value.copy(deep=True), var_type=var_type)
            else:
                new_ctx.vars.set(name, copy.copy(value), var_type=var_type)
        return new_ctx

    def branch(self) -> "SessionContext":
        """Fork from current state (convenience: checkpoint + branch_from)."""
        import uuid
        _temp = f"__branch__{uuid.uuid4().hex}__"
        self.checkpoint(_temp)
        branched = self.branch_from(_temp)
        del self._checkpoints[_temp]
        return branched

    def list_checkpoints(self) -> list[str]:
        return list(self._checkpoints.keys())

    def mark_active(self) -> None:
        self.last_active = time.monotonic()

    def steer(self, message: str) -> None:
        """Enqueue a steering message from an external source (e.g. IM follow-up)."""
        self._steering_queue.put_nowait(message)

    def drain_steerings(self) -> list[str]:
        """Drain all pending steering messages. Returns empty list if none."""
        messages: list[str] = []
        while not self._steering_queue.empty():
            try:
                messages.append(self._steering_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def set_channel_origin(self, origin: str) -> None:
        self.channel_origin = origin
