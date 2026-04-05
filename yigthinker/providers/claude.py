from __future__ import annotations
from collections.abc import AsyncIterator
import anthropic
from yigthinker.types import LLMResponse, Message, StreamEvent, ToolUse
from yigthinker.providers.base import LLMProvider


class ClaudeProvider:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def chat(self, messages: list[Message], tools: list[dict], system: str | None = None) -> LLMResponse:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=8192,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)
        return self._parse(response)

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=8192,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield StreamEvent(type="text", text=event.text)
                    elif (
                        event.type == "content_block_stop"
                        and hasattr(event.content_block, "type")
                        and event.content_block.type == "tool_use"
                    ):
                        yield StreamEvent(
                            type="tool_use",
                            tool_use=ToolUse(
                                id=event.content_block.id,
                                name=event.content_block.name,
                                input=event.content_block.input,
                            ),
                        )
                final = await stream.get_final_message()
                yield StreamEvent(
                    type="done",
                    stop_reason=final.stop_reason or "end_turn",
                )
        except Exception as e:
            yield StreamEvent(type="error", error=str(e))

    def _parse(self, response: anthropic.types.Message) -> LLMResponse:
        text = ""
        tool_uses: list[ToolUse] = []
        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_uses.append(ToolUse(id=block.id, name=block.name, input=block.input))
        return LLMResponse(
            stop_reason=response.stop_reason,  # type: ignore[arg-type]
            text=text,
            tool_uses=tool_uses,
        )
