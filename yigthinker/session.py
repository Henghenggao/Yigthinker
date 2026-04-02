from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from yigthinker.stats import StatsAccumulator
from yigthinker.types import Message


@dataclass
class VarInfo:
    name: str
    shape: tuple[int, ...]
    dtypes: dict[str, str]


class VarRegistry:
    """Session-scoped in-memory store for DataFrames and chart artifacts."""

    def __init__(self) -> None:
        self._vars: dict[str, Any] = {}

    def set(self, name: str, value: Any) -> None:
        self._vars[name] = value

    def get(self, name: str) -> Any:
        if name not in self._vars:
            available = list(self._vars)
            raise KeyError(f"Variable '{name}' not found. Available: {available}")
        return self._vars[name]

    def list(self) -> list[VarInfo]:
        infos: list[VarInfo] = []
        for name, value in self._vars.items():
            if isinstance(value, pd.DataFrame):
                infos.append(
                    VarInfo(
                        name=name,
                        shape=value.shape,
                        dtypes={col: str(dtype) for col, dtype in value.dtypes.items()},
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
    vars: VarRegistry = field(default_factory=VarRegistry)
    stats: StatsAccumulator = field(default_factory=StatsAccumulator)
    messages: list[Message] = field(default_factory=list)
