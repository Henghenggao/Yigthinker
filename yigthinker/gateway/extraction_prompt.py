"""Extraction-only LLM prompt for /api/rpa/callback (Phase 10 D-05).

Plan 10-02: The extraction LLM call uses `LLMProvider.chat(messages, tools=[],
system=EXTRACTION_SYSTEM)` to classify a checkpoint failure into one of three
actions (fix_applied, skip, escalate). The LLM MUST reply with a JSON object
and nothing else; `parse_extraction_response` wraps the parse in a layered
fallback that silently escalates on any parse or shape failure (CORR-04b).

No tools. No prose. No keyword heuristics. Pure structured JSON in/out.
"""
from __future__ import annotations

import json
import re
from typing import Any

EXTRACTION_SYSTEM = """\
You are an error-classification assistant for a data-analysis workflow runtime.
When a running script hits a checkpoint failure, you receive the error details
and respond with a JSON decision. Output JSON ONLY. No prose, no markdown fences.

Schema:
{
    "action": "fix_applied" | "skip" | "escalate",
    "instruction": "<human-readable next step, one sentence>",
    "retry_delay_s": <integer seconds, REQUIRED when action=fix_applied, null otherwise>,
    "reason": "<short classification reason, 1-3 words, snake_case>"
}

Decision rules:
- Network or transient I/O errors (ConnectionError, TimeoutError, socket errors, ConnectionRefusedError):
    action=fix_applied, retry_delay_s=5, reason="transient_network"
- File-not-found for optional paths (FileNotFoundError on *.cache, *.tmp, reports/*, scratch/*):
    action=skip, reason="missing_optional_file"
- Programming errors (KeyError, ValueError, TypeError, AttributeError, IndexError, column or key mismatch):
    action=escalate, reason="programming_error"
- Resource or permission errors (OSError disk full, MemoryError, PermissionError, Errno 13):
    action=escalate, reason="resource_or_permission"
- Anything else or ambiguous:
    action=escalate, reason="unclassified"

Examples:

Input: {"error_type": "ConnectionError", "error_message": "Connection refused", "checkpoint_id": "fetch_sales", "attempt_number": 1}
Output: {"action": "fix_applied", "instruction": "Wait and retry; database briefly unreachable.", "retry_delay_s": 5, "reason": "transient_network"}

Input: {"error_type": "KeyError", "error_message": "'revenue_2025'", "checkpoint_id": "aggregate_monthly", "attempt_number": 2}
Output: {"action": "escalate", "instruction": "Column 'revenue_2025' missing from source data; schema update required.", "retry_delay_s": null, "reason": "programming_error"}

Input: {"error_type": "FileNotFoundError", "error_message": "No such file: reports/.cache/stats.json", "checkpoint_id": "load_cache", "attempt_number": 1}
Output: {"action": "skip", "instruction": "Optional cache file missing; continuing without it.", "retry_delay_s": null, "reason": "missing_optional_file"}

Reply with the JSON object only. Do not wrap it in markdown. Do not add commentary.
"""


_VALID_ACTIONS = ("fix_applied", "skip", "escalate")


def _fail(reason_detail: str) -> dict[str, Any]:
    """Construct the canonical 'extraction_failed' escalate dict (CORR-04b)."""
    diag = reason_detail[:200] if reason_detail else "LLM response could not be parsed."
    return {
        "action": "escalate",
        "instruction": f"LLM response could not be parsed as a structured decision: {diag}",
        "retry_delay_s": None,
        "reason": "extraction_failed",
    }


def _try_json(candidate: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def parse_extraction_response(text: str) -> dict[str, Any]:
    """Parse an extraction LLM response into a decision dict.

    Layered fallback (CORR-04b — NO keyword heuristics):
      1. Direct json.loads(text)
      2. Strip markdown fences and language tag, retry
      3. Regex-extract the first {...} block, retry
      4. On any failure or unknown action value → escalate with reason='extraction_failed'
    """
    if not isinstance(text, str) or not text or not text.strip():
        return _fail("empty LLM response")

    raw = text.strip()

    # Fallback 1: direct parse
    obj = _try_json(raw)

    # Fallback 2: strip markdown code fences (```json ... ``` or ``` ... ```)
    if obj is None:
        stripped = raw
        if stripped.startswith("```"):
            # drop the opening fence line and any trailing fence
            stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
            stripped = re.sub(r"\n?```\s*$", "", stripped)
        obj = _try_json(stripped)

    # Fallback 3: regex-extract the first balanced-ish {...} block
    if obj is None:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m is not None:
            obj = _try_json(m.group(0))

    if obj is None:
        return _fail(raw[:200])

    # Shape validation
    action = obj.get("action")
    if action not in _VALID_ACTIONS:
        return _fail(f"unknown action: {action!r}")

    instruction = obj.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        return _fail("missing or empty 'instruction' field")

    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return _fail("missing or empty 'reason' field")

    retry_delay_s = obj.get("retry_delay_s")
    if action == "fix_applied":
        if not isinstance(retry_delay_s, int) or retry_delay_s < 0:
            # fix_applied without a sane delay → still escalate, we can't retry blindly
            return _fail("fix_applied action missing valid retry_delay_s")
    else:
        retry_delay_s = None

    return {
        "action": action,
        "instruction": instruction.strip(),
        "retry_delay_s": retry_delay_s,
        "reason": reason.strip(),
    }
