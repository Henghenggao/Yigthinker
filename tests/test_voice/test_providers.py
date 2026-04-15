from __future__ import annotations
from unittest.mock import AsyncMock, patch
from yigthinker.voice.providers import WhisperProvider, VoiceConfig


def test_voice_config_defaults():
    cfg = VoiceConfig()
    assert cfg.provider == "whisper"
    assert cfg.language == "zh"
    assert cfg.silence_detection_ms == 2000


async def test_whisper_provider_transcribes(tmp_path):
    config = VoiceConfig(language="zh")
    provider = WhisperProvider(config=config)
    with patch.object(provider, "_call_api", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = "看一下华东区上个季度的应收账龄分布"
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)
    assert "华东" in result or result == "看一下华东区上个季度的应收账龄分布"


async def test_whisper_provider_returns_empty_on_error():
    config = VoiceConfig()
    provider = WhisperProvider(config=config)
    with patch.object(provider, "_call_api", side_effect=Exception("API error")):
        result = await provider.transcribe(audio_bytes=b"\x00" * 1024)
    assert result == ""
