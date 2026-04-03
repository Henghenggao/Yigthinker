"""Gateway authentication via file-backed token."""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)


class GatewayAuth:
    """Manages a single gateway-level bearer token.

    On first start a random 64-hex-char token is generated and written to
    ``~/.yigthinker/gateway.token``.  All HTTP/WS requests must present this
    token.  Channel adapters use their own platform-specific secrets separately.
    """

    def __init__(self, token_path: Path | None = None) -> None:
        self._path = token_path or (Path.home() / ".yigthinker" / "gateway.token")
        self._token = self._load_or_create()

    @property
    def token(self) -> str:
        return self._token

    def verify(self, candidate: str) -> bool:
        """Constant-time comparison to prevent timing attacks."""
        return secrets.compare_digest(self._token, candidate)

    def _load_or_create(self) -> str:
        if self._path.exists():
            token = self._path.read_text(encoding="utf-8").strip()
            if token:
                return token

        token = secrets.token_hex(32)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(token, encoding="utf-8")

        # Best-effort chmod 600 (no-op on Windows)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

        logger.info("Generated new gateway token at %s", self._path)
        return token
