from __future__ import annotations

from pathlib import Path

import pytest

from yigthinker.memory.provider import FileMemoryProvider, MemoryProvider


def test_null_provider_returns_none():
    from yigthinker.builder import build_memory_provider
    provider = build_memory_provider({"memory": {"provider": "null"}})
    assert provider is None


def test_file_provider_instantiates(tmp_path: Path):
    from yigthinker.builder import build_memory_provider
    settings = {
        "memory": {
            "provider": "file",
            "file": {
                "store_dir": str(tmp_path),
                "agent_id": "test",
                "max_records_before_compact": 100,
            },
        }
    }
    provider = build_memory_provider(settings)
    assert isinstance(provider, FileMemoryProvider)
    assert isinstance(provider, MemoryProvider)   # Protocol check


def test_unknown_provider_raises():
    from yigthinker.builder import build_memory_provider
    with pytest.raises(ValueError, match="unknown memory provider"):
        build_memory_provider({"memory": {"provider": "sqlite-vec"}})


def test_missing_memory_config_defaults_to_none():
    from yigthinker.builder import build_memory_provider
    assert build_memory_provider({}) is None
