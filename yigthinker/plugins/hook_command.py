from __future__ import annotations

import asyncio
import json
import shlex
import sys

from yigthinker.types import HookAction, HookEvent, HookResult


class CommandHook:
    """Runs an external command as a hook.

    Exit codes: 0 = ALLOW, 1 = WARN (stderr → message), 2 = BLOCK (stderr → reason).
    The HookEvent is serialised to JSON and passed on stdin.
    """

    def __init__(self, command: str) -> None:
        self._command = command

    async def __call__(self, event: HookEvent) -> HookResult:
        payload = json.dumps({
            "event_type": event.event_type,
            "session_id": event.session_id,
            "tool_name": event.tool_name,
            "tool_input": event.tool_input,
        }).encode()

        try:
            # Replace create_subprocess_shell with exec to avoid shell injection
            if sys.platform == "win32":
                args = ["cmd", "/c"] + shlex.split(self._command, posix=False)
            else:
                args = shlex.split(self._command)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate(input=payload)
            message = stderr.decode(errors="replace").strip()

            if proc.returncode == 2:
                return HookResult.block(message or "Blocked by plugin hook")
            if proc.returncode == 1:
                return HookResult.warn(message or "Plugin hook warning")
            return HookResult.ALLOW
        except Exception as exc:
            return HookResult.warn(f"Plugin hook error: {exc}")
