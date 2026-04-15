from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from yigthinker.types import Message


@dataclass
class SpeculationConfig:
    enabled: bool = False
    max_candidates: int = 3
    max_turns_per_candidate: int = 3
    timeout_seconds: float = 15.0
    match_threshold: float = 0.85
    predictor_model: str = "claude-haiku-4-5-20251001"


@dataclass
class CandidateResult:
    prompt: str
    response: str
    tool_results: list[dict] = field(default_factory=list)


class SpeculationEngine:
    def __init__(self, config: SpeculationConfig | None = None) -> None:
        self._cfg = config or SpeculationConfig()
        self.stats: dict[str, int] = {"hits": 0, "misses": 0, "time_saved_ms": 0}

    def is_enabled(self) -> bool:
        return self._cfg.enabled

    async def predict_and_precompute(
        self,
        conversation: list[Message],
        vars_summary: str,
        provider: Any,
    ) -> list[CandidateResult]:
        """Predict next inputs and pre-compute responses. Returns [] if disabled."""
        if not self._cfg.enabled or provider is None:
            return []
        # Stub: production implementation spawns lightweight agent loops
        return []

    def match(
        self,
        actual_input: str,
        candidates: list[CandidateResult],
    ) -> CandidateResult | None:
        """Find best matching candidate using Jaccard similarity. Returns None on miss."""
        if not candidates:
            return None

        best: CandidateResult | None = None
        best_score = 0.0

        for candidate in candidates:
            score = self._similarity(actual_input, candidate.prompt)
            if score > best_score:
                best_score = score
                best = candidate

        if best_score >= self._cfg.match_threshold:
            return best
        return None

    def _similarity(self, a: str, b: str) -> float:
        """Jaccard similarity on token sets (fallback when no embedding model)."""
        a_tokens = set(a.lower().split())
        b_tokens = set(b.lower().split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens
        return len(intersection) / len(union)

    def record_hit(self, time_saved_ms: int = 0) -> None:
        self.stats["hits"] += 1
        self.stats["time_saved_ms"] += time_saved_ms

    def record_miss(self) -> None:
        self.stats["misses"] += 1
