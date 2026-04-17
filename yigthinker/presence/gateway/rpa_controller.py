"""RPAController — orchestrates the /api/rpa/callback and /api/rpa/report flows.

Plan 10-01: Full dedup + circuit breaker + handle_report landed.
Plan 10-02: Real extraction-only LLM call in _extract_decision via
LLMProvider.chat(messages, tools=[], system=EXTRACTION_SYSTEM). CORR-04b:
parse/network failures silently escalate with reason='extraction_failed'.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from yigthinker.presence.gateway.extraction_prompt import (
    EXTRACTION_SYSTEM,
    parse_extraction_response,
)
from yigthinker.types import Message

if TYPE_CHECKING:
    from yigthinker.presence.gateway.rpa_state import RPAStateStore
    from yigthinker.core.providers import LLMProvider
    from yigthinker.core.workflow import WorkflowRegistry

logger = logging.getLogger(__name__)

# Circuit breaker constants (Phase 10 CONTEXT.md D-03 / GW-RPA-04)
MAX_ATTEMPTS_24H = 3
MAX_LLM_CALLS_DAY = 10

# 30-day window for lazy rollover in handle_report (D-10)
ROLLOVER_WINDOW_DAYS = 30


class RPAController:
    """Orchestrates RPA callback + report flows."""

    def __init__(
        self,
        state: "RPAStateStore",
        registry: "WorkflowRegistry",
        provider: "LLMProvider",
    ) -> None:
        self._state = state
        self._registry = registry
        self._provider = provider

    # ──────────────────────────────────────────────────────────────────
    # /api/rpa/callback — self-healing
    # ──────────────────────────────────────────────────────────────────
    async def handle_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        callback_id = str(payload.get("callback_id") or "")
        workflow_name = str(payload.get("workflow_name") or "")
        checkpoint_id = str(payload.get("checkpoint_id") or "")

        if not callback_id or not workflow_name or not checkpoint_id:
            return {
                "action": "escalate",
                "instruction": "Callback payload missing required fields.",
                "retry_delay_s": None,
                "reason": "invalid_payload",
            }

        # 1. Dedup check — return cached decision if seen before
        if self._state.is_duplicate_callback(callback_id):
            cached = self._state.get_cached_decision(callback_id)
            if cached is not None:
                return cached
            # Fall through if cache corrupted

        # 2. Circuit breaker: checkpoint attempts (rolling 24h)
        attempts = self._state.record_checkpoint_attempt(workflow_name, checkpoint_id)
        if attempts > MAX_ATTEMPTS_24H:
            decision = {
                "action": "escalate",
                "instruction": (
                    f"Circuit breaker limit reached: "
                    f"{attempts} attempts on checkpoint '{checkpoint_id}' in 24h "
                    f"(max {MAX_ATTEMPTS_24H}). Human intervention required."
                ),
                "retry_delay_s": None,
                "reason": "breaker_exceeded",
            }
            self._state.record_callback(callback_id, decision)
            return decision

        # 3. Circuit breaker: daily LLM call budget (D-07 — count even on stub)
        llm_count = self._state.record_llm_call(workflow_name)
        if llm_count > MAX_LLM_CALLS_DAY:
            decision = {
                "action": "escalate",
                "instruction": (
                    f"Circuit breaker limit reached: "
                    f"{llm_count} LLM calls for workflow '{workflow_name}' today "
                    f"(max {MAX_LLM_CALLS_DAY}). Human intervention required."
                ),
                "retry_delay_s": None,
                "reason": "breaker_exceeded",
            }
            self._state.record_callback(callback_id, decision)
            return decision

        # 4. Real extraction LLM call (Plan 10-02, D-05)
        decision = await self._extract_decision(payload)

        # 5. Cache for future dedup hits
        self._state.record_callback(callback_id, decision)
        return decision

    async def _extract_decision(
        self, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Call the LLM with NO tools to classify the checkpoint error.

        Uniform across all 4 providers (Claude/OpenAI/Ollama/Azure) via
        `LLMProvider.chat(messages, tools=[], system=...)`. CORR-04b: on any
        parse or network failure, silently escalate with reason='extraction_failed'.
        """
        # Build the classification-only user message. Include exactly the
        # fields the extraction rules need — not workflow_name / callback_id
        # (those are routing keys, not classification signals).
        traceback_raw = str(payload.get("traceback") or "")
        user_payload = {
            "error_type": payload.get("error_type"),
            "error_message": payload.get("error_message"),
            "traceback": traceback_raw[:2000],   # D-05 budget cap
            "checkpoint_id": payload.get("checkpoint_id"),
            "attempt_number": payload.get("attempt_number"),
            "step_context": payload.get("step_context", {}),
        }
        user_msg = json.dumps(user_payload, ensure_ascii=False)

        try:
            response = await self._provider.chat(
                messages=[Message(role="user", content=user_msg)],
                tools=[],
                system=EXTRACTION_SYSTEM,
            )
        except Exception as exc:
            logger.warning("Extraction LLM call failed: %s", exc)
            return {
                "action": "escalate",
                "instruction": f"Extraction LLM call failed: {type(exc).__name__}",
                "retry_delay_s": None,
                "reason": "extraction_failed",
            }

        response_text = getattr(response, "text", None) or ""
        return parse_extraction_response(response_text)

    # ──────────────────────────────────────────────────────────────────
    # /api/rpa/report — telemetry write-path (NO LLM)
    # ──────────────────────────────────────────────────────────────────
    async def handle_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_name = str(payload.get("workflow_name") or "")
        finished_at = str(payload.get("finished_at") or "")
        status = str(payload.get("status") or "")

        if not workflow_name or not finished_at or status not in (
            "success", "failure", "partial",
        ):
            return {"ok": False, "error": "invalid_payload"}

        # Read existing entry for lazy rollover
        try:
            index = self._registry.load_index()
        except Exception:
            logger.exception("handle_report failed to load registry index")
            return {"ok": False, "error": "registry_read_failed"}

        existing_entry = index.get("workflows", {}).get(workflow_name, {}) or {}
        existing_run_count = int(existing_entry.get("run_count_30d") or 0)
        existing_failure_count = int(existing_entry.get("failure_count_30d") or 0)
        existing_last_run = existing_entry.get("last_run")

        # Lazy 30-day rollover (D-10): if existing last_run is > 30 days old,
        # reset the counters before incrementing.
        now = datetime.now(timezone.utc)
        if existing_last_run:
            try:
                prev = datetime.fromisoformat(str(existing_last_run))
                if prev.tzinfo is None:
                    prev = prev.replace(tzinfo=timezone.utc)
                if (now - prev) > timedelta(days=ROLLOVER_WINDOW_DAYS):
                    existing_run_count = 0
                    existing_failure_count = 0
            except Exception:
                # Unparseable timestamp — fall through and increment as usual
                pass

        new_run_count = existing_run_count + 1
        new_failure_count = existing_failure_count + (
            1 if status == "failure" else 0
        )

        patch = {
            "workflows": {
                workflow_name: {
                    "last_run": finished_at,
                    "last_run_status": status,
                    "run_count_30d": new_run_count,
                    "failure_count_30d": new_failure_count,
                }
            }
        }
        try:
            self._registry.save_index(patch)
        except Exception:
            logger.exception("handle_report save_index failed")
            return {"ok": False, "error": "registry_write_failed"}

        return {"ok": True}
