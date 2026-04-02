import pytest
from unittest.mock import patch

from yigthinker.providers.azure import AzureProvider
from yigthinker.providers.claude import ClaudeProvider
from yigthinker.providers.factory import provider_from_settings
from yigthinker.providers.ollama import OllamaProvider
from yigthinker.providers.openai import OpenAIProvider


def test_claude_provider():
    settings = {"model": "claude-sonnet-4-20250514"}
    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic"):
        provider = provider_from_settings(settings)
    assert isinstance(provider, ClaudeProvider)


def test_openai_provider():
    settings = {"model": "gpt-4o"}
    with patch("yigthinker.providers.openai.openai.AsyncOpenAI"):
        provider = provider_from_settings(settings)
    assert isinstance(provider, OpenAIProvider)


def test_ollama_provider():
    settings = {"model": "ollama/llama3", "ollama_base_url": "http://localhost:11434"}
    provider = provider_from_settings(settings)
    assert isinstance(provider, OllamaProvider)


def test_azure_provider():
    settings = {"model": "azure/my-deployment", "azure_endpoint": "https://example.openai.azure.com"}
    with patch("yigthinker.providers.azure.openai.AsyncAzureOpenAI"):
        provider = provider_from_settings(settings)
    assert isinstance(provider, AzureProvider)


def test_unknown_model_raises():
    settings = {"model": "unknown-vendor/model-xyz"}
    with pytest.raises(ValueError, match="Cannot determine LLM provider"):
        provider_from_settings(settings)
