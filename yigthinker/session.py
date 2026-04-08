from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    subagent_manager: SubagentManager | None = None

    def mark_active(self) -> None:
        self.last_active = time.monotonic()

    def set_channel_origin(self, origin: str) -> None:
        self.channel_origin = origin
