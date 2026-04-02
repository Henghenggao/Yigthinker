from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from yigthinker.voice.keyterms import build_keyterm_list


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


class WhisperProvider:
    """Whisper-based STT (OpenAI API or local faster-whisper)."""

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._keyterms = build_keyterm_list(config.custom_keyterms)

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes. Returns empty string on error."""
        try:
            return await self._call_api(audio_bytes)
        except Exception:
            return ""

    async def _call_api(self, audio_bytes: bytes) -> str:
        """Call Whisper API. Override in tests."""
        raise NotImplementedError("Whisper API not configured")
