"""Voice provider: Whisper-backed STT.

Honesty contract (2026-04-17): this provider fails loudly. If the OpenAI API
key is not configured, `transcribe()` raises `VoiceNotConfiguredError` with a
message telling the user what to set. API errors (network, rate limit,
authentication) propagate to the caller unchanged. The only case that
legitimately returns an empty string is when the Whisper API itself reports
"no speech detected."

Rationale (from TODOs.md): "Silent failure is worse than an explicit
unsupported message." The pre-2026-04-17 stub caught every exception and
returned "" — indistinguishable from legitimate silence and impossible to
debug.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Literal

from yigthinker.voice.keyterms import build_keyterm_list

# Lazy-imported at call-site to keep openai optional for non-voice users;
# re-exported here under the name `AsyncOpenAI` so tests can patch this
# module-level symbol.
try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - openai is in core deps but guarded
    AsyncOpenAI = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class VoiceError(Exception):
    """Base class for voice provider errors."""


class VoiceNotConfiguredError(VoiceError):
    """Raised when voice transcription is invoked without required config.

    Carries an actionable message naming the missing env var / kwarg.
    """


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TranscriptEvent:
    type: Literal["interim", "final", "endpoint", "error"]
    text: str
    confidence: float = 1.0


@dataclass
class VoiceConfig:
    provider: str = "whisper"
    language: str = "zh"
    custom_keyterms: list[str] = field(default_factory=list)
    inject_schema_keyterms: bool = True
    inject_entity_names: bool = False
    silence_detection_ms: int = 2000
    # Whisper model name; whisper-1 is OpenAI's only publicly-priced model as
    # of writing. Kept configurable so self-hosted variants can swap it.
    model: str = "whisper-1"


# ---------------------------------------------------------------------------
# WhisperProvider
# ---------------------------------------------------------------------------

class WhisperProvider:
    """Whisper STT via OpenAI Audio API.

    Construction is cheap — the HTTP client is built lazily on the first
    transcribe() call so unit tests can instantiate providers freely.
    """

    def __init__(
        self,
        config: VoiceConfig,
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._keyterms = build_keyterm_list(config.custom_keyterms)
        # Resolve the API key eagerly so construction doesn't hide a later
        # failure. If both kwarg and env var are absent, transcribe() will
        # surface VoiceNotConfiguredError on first call (not here — callers
        # should be able to build a provider lazily without an API key
        # sitting in the environment during object graph assembly).
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe PCM audio bytes to text.

        Raises:
            VoiceNotConfiguredError: if no OpenAI API key is configured.
            Exception: API / network errors from the OpenAI SDK propagate
              unchanged. Callers decide how to recover.

        Returns:
            The transcribed text, or an empty string only when the API
            itself reports no speech detected. Empty-string is NEVER a
            catch-all for errors (see module docstring).
        """
        if not self._api_key:
            raise VoiceNotConfiguredError(
                "Voice transcription requested but no OpenAI API key is "
                "configured. Set the OPENAI_API_KEY environment variable "
                "or pass api_key=... to WhisperProvider(...)."
            )
        return await self._call_api(audio_bytes)

    async def _call_api(self, audio_bytes: bytes) -> str:
        """Call the OpenAI Audio transcription endpoint.

        Separated from transcribe() so tests can mock the network layer
        while still exercising the configuration-check path.
        """
        if AsyncOpenAI is None:  # pragma: no cover - openai is in core deps
            raise VoiceNotConfiguredError(
                "openai package not installed. Install with: pip install openai"
            )
        client = AsyncOpenAI(api_key=self._api_key)
        # OpenAI SDK expects a file-like with a .name attribute so it can
        # infer the MIME type. Wrap raw PCM bytes in a BytesIO and give it
        # a .wav-like name; for production PCM should be containerized
        # before call, but the caller controls that — we just hand off.
        buf = io.BytesIO(audio_bytes)
        buf.name = "audio.wav"
        response = await client.audio.transcriptions.create(
            model=self._config.model,
            file=buf,
            language=self._config.language,
        )
        # OpenAI SDK returns a Transcription object with .text; some
        # variants may return a raw string. Accept either.
        return getattr(response, "text", response) or ""
