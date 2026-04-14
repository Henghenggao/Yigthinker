from __future__ import annotations

import os
from typing import Any

from yigthinker.providers.base import LLMProvider


def provider_from_settings(settings: dict[str, Any]) -> LLMProvider:
    """Instantiate the appropriate LLM provider from settings."""
    model = settings.get("model", "")

    if model.startswith("claude"):
        from yigthinker.providers.claude import ClaudeProvider
        from yigthinker.types import ThinkingConfig

        thinking_cfg = settings.get("thinking", {})
        thinking = ThinkingConfig(
            enabled=thinking_cfg.get("enabled", False),
            budget_tokens=thinking_cfg.get("budget_tokens", 10000),
        )
        return ClaudeProvider(model=model, api_key=os.environ.get("ANTHROPIC_API_KEY"), thinking=thinking)

    if model.startswith(("gpt-", "o1", "o3", "o4")):
        from yigthinker.providers.openai import OpenAIProvider

        return OpenAIProvider(model=model, api_key=os.environ.get("OPENAI_API_KEY"))

    if model.startswith("ollama/"):
        from yigthinker.providers.ollama import OllamaProvider

        return OllamaProvider(
            model=model[len("ollama/"):],
            base_url=settings.get("ollama_base_url", "http://localhost:11434"),
        )

    if model.startswith("azure/"):
        from yigthinker.providers.azure import AzureProvider

        return AzureProvider(
            deployment_name=model[len("azure/"):],
            api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=settings.get("azure_endpoint", ""),
            api_version=settings.get("azure_api_version", "2024-02-01"),
        )

    raise ValueError(
        f"Cannot determine LLM provider for model '{model}'. "
        "Expected prefix: 'claude', 'gpt-', 'ollama/', or 'azure/'"
    )
