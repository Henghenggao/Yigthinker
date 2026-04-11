"""httpx.AsyncClient wrapper around UiPath Orchestrator OData v20.10+ endpoints.

Implemented in Plan 11-03 per CONTEXT.md D-12..D-14.
Will expose ``OrchestratorClient(auth, base_url)`` with retry/timeout logic.
"""
from __future__ import annotations
