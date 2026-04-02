from __future__ import annotations

import json

import openai

from yigthinker.types import LLMResponse, Message, ToolUse


class OpenAIProvider:
    """LLM provider for OpenAI chat-completions-compatible models."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def chat(self, messages: list[Message], tools: list[dict], system: str | None = None) -> LLMResponse:
        converted = self._convert_messages(messages)
        if system:
            converted = [{"role": "system", "content": system}] + converted
        kwargs: dict = {
            "model": self._model,
            "messages": converted,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
                for tool in tools
            ]
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        return self._parse(response)

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        converted: list[dict] = []
        for message in messages:
            if isinstance(message.content, str):
                converted.append({"role": message.role, "content": message.content})
                continue

            if isinstance(message.content, list):
                if message.role == "assistant":
                    text_parts: list[str] = []
                    tool_calls: list[dict] = []
                    for block in message.content:
                        if not isinstance(block, dict):
                            text_parts.append(str(block))
                            continue
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                            continue
                        if block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block["id"],
                                    "type": "function",
                                    "function": {
                                        "name": block["name"],
                                        "arguments": json.dumps(block["input"]),
                                    },
                                }
                            )
                    assistant_message: dict = {
                        "role": "assistant",
                        "content": "\n".join(part for part in text_parts if part),
                    }
                    if tool_calls:
                        assistant_message["tool_calls"] = tool_calls
                    converted.append(assistant_message)
                    continue

                for block in message.content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        converted.append(
                            {
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block["content"],
                            }
                        )
                    else:
                        converted.append({"role": message.role, "content": str(block)})
                continue

            converted.append({"role": message.role, "content": str(message.content)})
        return converted

    def _parse(self, response) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message
        tool_uses: list[ToolUse] = []
        for tool_call in message.tool_calls or []:
            tool_uses.append(
                ToolUse(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    input=json.loads(tool_call.function.arguments),
                )
            )

        stop_reason = "tool_use" if tool_uses else "end_turn"
        return LLMResponse(
            stop_reason=stop_reason,
            text=message.content or "",
            tool_uses=tool_uses,
        )
