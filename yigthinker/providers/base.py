from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable
from yigthinker.types import LLMResponse, Message, StreamEvent


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(self, messages: list[Message], tools: list[dict], system: str | None = None) -> LLMResponse: ...
    async def stream(self, messages: list[Message], tools: list[dict], system: str | None = None) -> AsyncIterator[StreamEvent]: ...
