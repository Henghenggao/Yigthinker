from __future__ import annotations
from yigthinker.speculation.engine import SpeculationEngine, SpeculationConfig, CandidateResult


def test_speculation_config_defaults():
    cfg = SpeculationConfig()
    assert cfg.enabled is False
    assert cfg.max_candidates == 3
    assert cfg.match_threshold == 0.85
    assert cfg.timeout_seconds == 15


def test_speculation_disabled_by_default():
    engine = SpeculationEngine(SpeculationConfig(enabled=False))
    assert not engine.is_enabled()


async def test_speculation_skipped_when_disabled():
    engine = SpeculationEngine(SpeculationConfig(enabled=False))
    candidates = await engine.predict_and_precompute(
        conversation=[],
        vars_summary="",
        provider=None,
    )
    assert candidates == []


def test_match_exact():
    engine = SpeculationEngine(SpeculationConfig(enabled=True, match_threshold=0.0))
    candidates = [
        CandidateResult(prompt="show revenue by region", response="Revenue: ...", tool_results=[]),
        CandidateResult(prompt="list top customers", response="Customers: ...", tool_results=[]),
    ]
    hit = engine.match(actual_input="show revenue by region", candidates=candidates)
    assert hit is not None
    assert hit.prompt == "show revenue by region"


def test_match_no_hit_below_threshold():
    engine = SpeculationEngine(SpeculationConfig(enabled=True, match_threshold=0.99))
    candidates = [
        CandidateResult(prompt="show revenue by region", response="Revenue: ...", tool_results=[]),
    ]
    hit = engine.match(actual_input="what is the weather today", candidates=candidates)
    assert hit is None


def test_record_hit_and_miss():
    engine = SpeculationEngine(SpeculationConfig(enabled=True))
    engine.record_hit(time_saved_ms=500)
    engine.record_miss()
    engine.record_hit(time_saved_ms=300)
    assert engine.stats["hits"] == 2
    assert engine.stats["misses"] == 1
    assert engine.stats["time_saved_ms"] == 800
