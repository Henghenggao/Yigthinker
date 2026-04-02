from __future__ import annotations
import anthropic
from yigthinker.types import LLMResponse, Message, ToolUse
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
