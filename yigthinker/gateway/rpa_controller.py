"""RPAController — orchestrates the /api/rpa/callback and /api/rpa/report flows.

Plan 10-01: Full dedup + circuit breaker + handle_report; handle_callback's
extraction step is stubbed (always returns escalate/extraction_not_implemented).
Plan 10-02: Replace _extract_decision_stub with real LLMProvider.chat extraction.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yigthinker.gateway.rpa_state import RPAStateStore
    from yigthinker.providers.base import LLMProvider
    from yigthinker.tools.workflow.registry import WorkflowRegistry

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

        # 4. STUB: Plan 10-02 replaces this with real extraction LLM call
        decision = await self._extract_decision_stub(payload)

        # 5. Cache for future dedup hits
        self._state.record_callback(callback_id, decision)
        return decision

    async def _extract_decision_stub(
        self, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """STUB: Plan 10-02 replaces this with real LLMProvider.chat extraction.

        Do NOT rename — Plan 10-02 deletes this method by name.
        """
        return {
            "action": "escalate",
            "instruction": "Manual intervention needed",
            "retry_delay_s": None,
            "reason": "extraction_not_implemented",
        }

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
