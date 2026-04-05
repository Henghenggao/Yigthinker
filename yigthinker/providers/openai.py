from __future__ import annotations

import json
from collections.abc import AsyncIterator

import openai

from yigthinker.types import LLMResponse, Message, StreamEvent, ToolUse


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

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        converted = self._convert_messages(messages)
        if system:
            converted = [{"role": "system", "content": system}] + converted
        kwargs: dict = {
            "model": self._model,
            "messages": converted,
            "stream": True,
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

        try:
            response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            tool_call_accum: dict[int, dict] = {}

            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta and delta.content:
                    yield StreamEvent(type="text", text=delta.content)

                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {"id": "", "name": "", "args": ""}
                        if tc.id:
                            tool_call_accum[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_call_accum[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_call_accum[idx]["args"] += tc.function.arguments

                if choice.finish_reason == "tool_calls":
                    for tc_data in tool_call_accum.values():
                        yield StreamEvent(
                            type="tool_use",
                            tool_use=ToolUse(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                input=json.loads(tc_data["args"]) if tc_data["args"] else {},
                            ),
                        )
                    tool_call_accum.clear()

                if choice.finish_reason in ("stop", "tool_calls"):
                    yield StreamEvent(
                        type="done",
                        stop_reason="end_turn" if choice.finish_reason == "stop" else "tool_use",
                    )
        except Exception as e:
            yield StreamEvent(type="error", error=str(e))

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
