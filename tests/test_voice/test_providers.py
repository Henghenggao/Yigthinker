"""Tests for voice providers.

Historical note: before 2026-04-17 the WhisperProvider silently swallowed all
errors and returned "" — indistinguishable from legitimate silence. The old
`test_whisper_provider_returns_empty_on_error` test was removed because it
enshrined a honesty-gap behavior. TODOs.md: "Silent failure is worse than an
explicit unsupported message." The provider now fails loudly when
unconfigured and propagates OpenAI API errors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yigthinker.voice.providers import (
    VoiceConfig,
    VoiceError,
    VoiceNotConfiguredError,
    WhisperProvider,
)


# ---------------------------------------------------------------------------
# VoiceConfig — unchanged from prior version
# ---------------------------------------------------------------------------

def test_voice_config_defaults():
    cfg = VoiceConfig()
    assert cfg.provider == "whisper"
    assert cfg.language == "zh"
    assert cfg.silence_detection_ms == 2000


# ---------------------------------------------------------------------------
# WhisperProvider — loud-failure semantics
# ---------------------------------------------------------------------------

async def test_whisper_raises_when_openai_key_missing(monkeypatch):
    """If OPENAI_API_KEY is not set and no key was passed, transcribing must
    raise a clear VoiceNotConfiguredError telling the user what to do —
    NOT silently return ''."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = WhisperProvider(config=VoiceConfig(), api_key=None)

    with pytest.raises(VoiceNotConfiguredError) as exc_info:
        await provider.transcribe(audio_bytes=b"\x00" * 1024)

    # Error message must mention the env var OR the install hint so the
    # user has something actionable.
    msg = str(exc_info.value)
    assert "OPENAI_API_KEY" in msg or "api_key" in msg.lower()


async def test_whisper_accepts_api_key_via_argument(monkeypatch):
    """Explicit api_key kwarg must work even without env var."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = WhisperProvider(config=VoiceConfig(), api_key="sk-test")
    with patch.object(
        provider, "_call_api", new_callable=AsyncMock
    ) as mock_api:
        mock_api.return_value = "hello"
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)
    assert result == "hello"


async def test_whisper_reads_api_key_from_env(monkeypatch):
    """If api_key kwarg is None but env var is set, provider should pick
    that up — no error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
    provider = WhisperProvider(config=VoiceConfig(), api_key=None)
    with patch.object(
        provider, "_call_api", new_callable=AsyncMock
    ) as mock_api:
        mock_api.return_value = "from env"
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)
    assert result == "from env"


async def test_whisper_propagates_api_errors(monkeypatch):
    """API failures (network, rate limit, auth) must propagate — NOT be
    swallowed into an empty string. Caller chooses how to recover."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = WhisperProvider(config=VoiceConfig())

    class FakeAPIError(Exception):
        pass

    with patch.object(
        provider, "_call_api", side_effect=FakeAPIError("429 rate limit")
    ):
        with pytest.raises(FakeAPIError):
            await provider.transcribe(audio_bytes=b"\x00" * 1024)


async def test_whisper_returns_empty_for_legitimate_silence(monkeypatch):
    """An empty-string response from the API is a LEGITIMATE outcome
    (e.g. silent audio). Propagate it unchanged — do NOT treat as an error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = WhisperProvider(config=VoiceConfig())
    with patch.object(
        provider, "_call_api", new_callable=AsyncMock
    ) as mock_api:
        mock_api.return_value = ""  # API says: no speech detected
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)
    assert result == ""


# ---------------------------------------------------------------------------
# Real OpenAI client wiring (mocked at AsyncOpenAI level)
# ---------------------------------------------------------------------------

async def test_whisper_calls_openai_audio_api(monkeypatch):
    """_call_api must actually call openai.AsyncOpenAI().audio.transcriptions
    .create — not NotImplementedError. Mock at the SDK level to verify the
    wiring without hitting the network."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = WhisperProvider(config=VoiceConfig(language="zh"))

    fake_response = MagicMock()
    fake_response.text = "看一下华东区上个季度的应收账龄分布"
    mock_transcriptions = MagicMock()
    mock_transcriptions.create = AsyncMock(return_value=fake_response)
    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions
    mock_client = MagicMock()
    mock_client.audio = mock_audio

    with patch(
        "yigthinker.voice.providers.AsyncOpenAI", return_value=mock_client
    ):
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)

    assert "华东" in result
    # Verify the call shape: model, language, file were passed
    mock_transcriptions.create.assert_awaited_once()
    call_kwargs = mock_transcriptions.create.await_args.kwargs
    assert call_kwargs.get("language") == "zh"
    assert "file" in call_kwargs
    assert call_kwargs.get("model", "").startswith("whisper")


def test_voice_not_configured_error_is_subclass_of_voice_error():
    """Contract: VoiceNotConfiguredError must be catchable via VoiceError."""
    assert issubclass(VoiceNotConfiguredError, VoiceError)
