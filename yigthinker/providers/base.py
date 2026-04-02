from __future__ import annotations
from typing import Protocol, runtime_checkable
from yigthinker.types import LLMResponse, Message


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(self, messages: list[Message], tools: list[dict], system: str | None = None) -> LLMResponse: ...
