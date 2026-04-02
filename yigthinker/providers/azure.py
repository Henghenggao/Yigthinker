from __future__ import annotations

import openai

from yigthinker.providers.openai import OpenAIProvider


class AzureProvider(OpenAIProvider):
    """LLM provider for Azure OpenAI deployments."""

    def __init__(
        self,
        deployment_name: str,
        api_key: str,
        azure_endpoint: str,
        api_version: str = "2024-02-01",
    ) -> None:
        self._model = deployment_name
        self._client = openai.AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
