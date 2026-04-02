from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


@runtime_checkable
class YigthinkerTool(Protocol):
    name: str
    description: str
    input_schema: type[BaseModel]

    async def execute(self, input: BaseModel, ctx: SessionContext) -> ToolResult: ...
