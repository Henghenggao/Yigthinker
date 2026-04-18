"""SuggestAutomationTool — read-only workflow tool listing detected automation
opportunities from PatternStore.

Phase 10 / BHV-03 + BHV-04. Registered under the `workflow` feature gate alongside
WorkflowGenerateTool / WorkflowDeployTool / WorkflowManageTool. The LLM is nudged
to call this at turn-end by the BHV-01 system prompt directive (Plan 10-04).

Input (D-21):
    min_frequency: int = 2          # only patterns seen this many times
    include_suppressed: bool = False # default: hide suppressed entries
    dismiss: str | None = None       # shortcut: suppress(pid, days=90)

Output (D-21):
    {
        "suggestions": [
            {
                "pattern_id": str,
                "description": str,
                "tool_sequence": [str, ...],
                "frequency": int,
                "estimated_time_saved_minutes": int,
                "required_connections": [str, ...],
                "last_seen": str,
                "can_deploy_to": ["local", "power_automate"?, "uipath"?],
            },
            ...  # sorted by time_saved * frequency descending
        ],
        "summary": str,
    }

`can_deploy_to` is computed via `importlib.util.find_spec` — never via real import
(Pitfall from Phase 9 auto-mode detection, and D-21). The MCP modules
(`yigthinker_mcp_powerautomate`, `yigthinker_mcp_uipath`) are deliberately NOT
imported anywhere in this module.

When `dismiss` is provided, the tool short-circuits:
    {"dismissed": pattern_id, "ok": bool}
"""

from __future__ import annotations

import importlib.util
from typing import Any

from pydantic import BaseModel, Field

from yigthinker.memory.patterns import PatternStore
from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class SuggestAutomationInput(BaseModel):
    """Inputs for `suggest_automation`. All fields optional with sensible defaults."""

    min_frequency: int = Field(
        default=2,
        description="Only include patterns seen this many times or more.",
    )
    include_suppressed: bool = Field(
        default=False,
        description="If True, include patterns currently suppressed by the user.",
    )
    dismiss: str | None = Field(
        default=None,
        description=(
            "Shortcut: when provided, suppress this pattern_id for 90 days and "
            "return a confirmation instead of listing suggestions."
        ),
    )


class SuggestAutomationTool:
    """Read-only workflow tool surfacing detected automation opportunities."""

    name = "suggest_automation"
    description = (
        "List detected automation opportunities from cross-session pattern "
        "analysis. Each suggestion includes estimated time saved, execution "
        "frequency, required connections, and which RPA platforms can deploy it. "
        "Use `dismiss='<pattern_id>'` to suppress a suggestion for 90 days."
    )
    input_schema = SuggestAutomationInput

    def __init__(self, store: PatternStore) -> None:
        self._store = store

    async def execute(
        self,
        input: SuggestAutomationInput,
        ctx: SessionContext,
    ) -> ToolResult:
        try:
            # --- Dismiss shortcut (D-22) ---
            if input.dismiss:
                ok = self._store.suppress(input.dismiss, days=90)
                return ToolResult(
                    tool_use_id="",
                    content={"dismissed": input.dismiss, "ok": ok},
                )

            # --- Listing path (D-21) ---
            active = self._store.list_active(
                min_frequency=input.min_frequency,
                include_suppressed=input.include_suppressed,
            )
            deploy_targets = self._available_deploy_targets()

            suggestions: list[dict[str, Any]] = []
            for entry in active:
                pid = entry.get("pattern_id") or ""
                is_seed = str(pid).startswith("finance_seed:")
                suggestions.append(
                    {
                        "pattern_id": pid,
                        "description": entry.get("description"),
                        "tool_sequence": entry.get("tool_sequence", []),
                        "frequency": entry.get("frequency", 0),
                        "estimated_time_saved_minutes": entry.get(
                            "estimated_time_saved_minutes", 0
                        ),
                        "required_connections": entry.get("required_connections", []),
                        "last_seen": entry.get("last_seen"),
                        "can_deploy_to": list(deploy_targets),
                        # 2026-04-18 ADR-011 Track D: mark seeds so the LLM
                        # can narrate honestly (seeds are shipped baseline
                        # rituals, not patterns observed in the user's
                        # sessions).
                        "is_seed": is_seed,
                    }
                )

            # Sort: detected patterns (by biggest expected win)
            # first, then seeds (by standalone estimated_time_saved).
            # This matches user intent: "what have YOU seen me do that
            # I could automate" before "what CANONICAL rituals do you
            # ship." Detected patterns are higher signal.
            def _sort_key(s: dict[str, Any]) -> tuple:
                # Tuple sorts: non-seed first (False < True), then by
                # expected win descending (negate for descending).
                expected_win = (
                    s["estimated_time_saved_minutes"] * max(s["frequency"], 1)
                )
                return (s["is_seed"], -expected_win)

            suggestions.sort(key=_sort_key)

            # Compose an honest summary that distinguishes seeds from
            # detected patterns — no conflation, no false "N detected"
            # claims when most entries are shipped baselines.
            detected_count = sum(1 for s in suggestions if not s["is_seed"])
            seed_count = sum(1 for s in suggestions if s["is_seed"])

            if not suggestions:
                summary = (
                    "No automation opportunities available: no baseline "
                    "rituals are seeded and no repeat patterns have been "
                    "detected from your sessions yet."
                )
            else:
                parts: list[str] = []
                if detected_count:
                    top_detected = next(
                        s for s in suggestions if not s["is_seed"]
                    )
                    win = (
                        top_detected["estimated_time_saved_minutes"]
                        * top_detected["frequency"]
                    )
                    parts.append(
                        f"{detected_count} pattern"
                        f"{'s' if detected_count != 1 else ''} "
                        f"detected from your sessions "
                        f"(biggest: {top_detected['pattern_id']}, "
                        f"~{win} min saved)"
                    )
                if seed_count:
                    parts.append(
                        f"{seed_count} baseline finance ritual"
                        f"{'s' if seed_count != 1 else ''} "
                        f"shipped by Yigfinance (available as "
                        f"seed suggestions regardless of observation count)"
                    )
                summary = ". ".join(parts) + "."

            return ToolResult(
                tool_use_id="",
                content={"suggestions": suggestions, "summary": summary},
            )
        except Exception as exc:  # defensive — never crash the agent loop
            return ToolResult(
                tool_use_id="",
                content=f"suggest_automation failed: {exc}",
                is_error=True,
            )

    # ------------------------------------------------------------- internal

    def _available_deploy_targets(self) -> list[str]:
        """Compute deployable RPA targets via `importlib.util.find_spec` (D-21).

        NEVER imports the MCP module — that would trigger optional-dependency
        side effects. `find_spec` just checks whether the module is importable.
        """
        targets: list[str] = ["local"]
        if importlib.util.find_spec("yigthinker_mcp_powerautomate") is not None:
            targets.append("power_automate")
        if importlib.util.find_spec("yigthinker_mcp_uipath") is not None:
            targets.append("uipath")
        return targets
