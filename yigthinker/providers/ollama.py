from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
import uuid

import httpx

from yigthinker.types import LLMResponse, Message, StreamEvent, ToolUse


async def _http_post(url: str, payload: dict) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


class OllamaProvider:
    """LLM provider for Ollama chat-compatible models."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def chat(self, messages: list[Message], tools: list[dict], system: str | None = None) -> LLMResponse:
        converted = self._convert_messages(messages)
        if system:
            converted = [{"role": "system", "content": system}] + converted
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": converted,
            "stream": False,
        }
        if tools:
            payload["tools"] = [
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

        response = await _http_post(f"{self._base_url}/api/chat", payload)
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
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": converted,
            "stream": True,
        }
        if tools:
            payload["tools"] = [
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

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/chat", json=payload
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        msg = chunk.get("message", {})

                        if msg.get("content"):
                            yield StreamEvent(type="text", text=msg["content"])

                        if msg.get("tool_calls"):
                            for tc in msg["tool_calls"]:
                                fn = tc.get("function", {})
                                yield StreamEvent(
                                    type="tool_use",
                                    tool_use=ToolUse(
                                        id=uuid.uuid4().hex[:8],
                                        name=fn.get("name", ""),
                                        input=fn.get("arguments", {}),
                                    ),
                                )

                        if chunk.get("done"):
                            yield StreamEvent(
                                type="done",
                                stop_reason="tool_use" if msg.get("tool_calls") else "end_turn",
                            )
        except Exception as e:
            yield StreamEvent(type="error", error=str(e))

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message.content, str):
                converted.append({"role": message.role, "content": message.content})
                continue

            if isinstance(message.content, list):
                text_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for block in message.content:
                    if not isinstance(block, dict):
                        text_parts.append(str(block))
                        continue
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append(
                            {
                                "function": {
                                    "name": block["name"],
                                    "arguments": block["input"],
                                }
                            }
                        )
                    elif block.get("type") == "tool_result":
                        converted.append(
                            {
                                "role": "tool",
                                "content": block.get("content", ""),
                            }
                        )
                if text_parts or tool_calls:
                    payload: dict[str, Any] = {
                        "role": message.role,
                        "content": "\n".join(part for part in text_parts if part),
                    }
                    if tool_calls:
                        payload["tool_calls"] = tool_calls
                    converted.append(payload)
                continue

            converted.append({"role": message.role, "content": str(message.content)})
        return converted

    def _parse(self, response: dict[str, Any]) -> LLMResponse:
        message = response.get("message", {})
        tool_uses: list[ToolUse] = []
        for raw_tool_call in message.get("tool_calls") or []:
            function = raw_tool_call.get("function", {})
            arguments = function.get("arguments", {})
            tool_uses.append(
                ToolUse(
                    id=uuid.uuid4().hex[:8],
                    name=function.get("name", ""),
                    input=arguments if isinstance(arguments, dict) else {},
                )
            )

        stop_reason = "tool_use" if tool_uses else "end_turn"
        return LLMResponse(
            stop_reason=stop_reason,
            text=message.get("content") or "",
            tool_uses=tool_uses,
        )
