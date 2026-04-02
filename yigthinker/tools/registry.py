from __future__ import annotations
from yigthinker.tools.base import YigthinkerTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, YigthinkerTool] = {}

    def register(self, tool: YigthinkerTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> YigthinkerTool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered. Available: {list(self._tools)}")
        return self._tools[name]

    def export_schemas(self) -> list[dict]:
        """Export all tools as Anthropic-compatible tool definitions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def names(self) -> list[str]:
        return list(self._tools)
