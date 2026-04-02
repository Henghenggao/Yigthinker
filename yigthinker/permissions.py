from __future__ import annotations
import re
from typing import Literal

PermissionDecision = Literal["allow", "ask", "deny"]


class PermissionSystem:
    """Evaluates allow/ask/deny rules from settings.permissions.

    Rule priority (highest first): deny > allow > ask > default(ask).

    Pattern format:
      - "sql_query"              matches any sql_query call
      - "sql_query(DELETE:*)"    matches sql_query where first SQL keyword is DELETE
    """

    def __init__(self, permissions: dict[str, list[str]]) -> None:
        self._allow: list[str] = permissions.get("allow", [])
        self._ask: list[str] = permissions.get("ask", [])
        self._deny: list[str] = permissions.get("deny", [])
        self._session_overrides: dict[str, list[str]] = {}

    def allow_for_session(self, tool_name: str, session_id: str) -> None:
        """Grant session-scoped permission that doesn't affect other sessions."""
        self._session_overrides.setdefault(session_id, []).append(tool_name)

    def clear_session(self, session_id: str) -> None:
        """Clean up when session ends."""
        self._session_overrides.pop(session_id, None)

    def check(
        self,
        tool_name: str,
        tool_input: dict | None = None,
        session_id: str | None = None,
    ) -> PermissionDecision:
        call_repr = self._call_repr(tool_name, tool_input or {})

        for pattern in self._deny:
            if self._matches(pattern, call_repr):
                return "deny"

        for pattern in self._allow:
            if self._matches(pattern, call_repr):
                return "allow"

        # Check session-scoped overrides (after deny, after global allow, before ask)
        if session_id and session_id in self._session_overrides:
            if tool_name in self._session_overrides[session_id]:
                return "allow"

        for pattern in self._ask:
            if self._matches(pattern, call_repr):
                return "ask"

        return "ask"  # safe default

    def _call_repr(self, tool_name: str, tool_input: dict) -> str:
        """Build repr for pattern matching. sql_query → 'sql_query(KEYWORD:*)'."""
        if tool_name == "sql_query" and "query" in tool_input:
            query = str(tool_input["query"]).strip().upper()
            keyword = query.split()[0] if query.split() else ""
            return f"{tool_name}({keyword}:*)"
        return tool_name

    def _matches(self, pattern: str, call_repr: str) -> bool:
        """Glob-style match: '*' is a wildcard."""
        regex = re.escape(pattern).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, call_repr))
