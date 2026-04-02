from __future__ import annotations
from typing import Any
import httpx


async def _http_post(url: str, payload: dict) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.post(url, json=payload)
        return response.json()


class DashboardClient:
    """Pushes chart/table entries to the running Yigthinker Dashboard server."""

    def __init__(self, server_url: str = "http://localhost:8765") -> None:
        self._url = server_url.rstrip("/")

    async def push(
        self,
        dashboard_id: str,
        title: str,
        chart_json: str,
        description: str = "",
    ) -> dict[str, Any] | None:
        """POST entry to dashboard. Returns None silently if server unavailable."""
        try:
            return await _http_post(
                f"{self._url}/api/dashboard/push",
                {
                    "dashboard_id": dashboard_id,
                    "title": title,
                    "chart_json": chart_json,
                    "description": description,
                },
            )
        except Exception:
            return None
