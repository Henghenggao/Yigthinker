from __future__ import annotations

from dataclasses import dataclass
import json

from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool


@dataclass
class CommandResult:
    handled: bool
    output: str = ""


class CommandRouter:
    """Routes /slash commands to handlers."""

    def __init__(self, pool: ConnectionPool, extra_commands: dict[str, str] | None = None) -> None:
        self._pool = pool
        self._extra_commands = extra_commands or {}
        self._handlers = {
            "/vars": self._vars,
            "/help": self._help,
            "/connect": self._connect,
            "/schema": self._schema,
            "/history": self._history,
            "/export": self._export,
            "/schedule": self._schedule,
            "/stats": self._stats,
            "/advisor": self._advisor,
            "/voice": self._voice,
        }

    async def handle(self, text: str, ctx: SessionContext) -> CommandResult:
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handler = self._handlers.get(command)
        if handler is None:
            if command in self._extra_commands:
                rendered = self._extra_commands[command]
                if args:
                    rendered = f"{rendered}\n\nArguments: {args}"
                return CommandResult(handled=True, output=rendered)
            return CommandResult(handled=False)
        return CommandResult(handled=True, output=await handler(args, ctx))

    async def _vars(self, args: str, ctx: SessionContext) -> str:
        infos = ctx.vars.list()
        if not infos:
            return "No variables registered. Load data with df_load or sql_query first."
        lines = ["Variable Registry:"]
        for info in infos:
            shape_str = f"{info.shape[0]}x{info.shape[1]}" if len(info.shape) == 2 else str(info.shape)
            cols = ", ".join(list(info.dtypes)[:5])
            lines.append(f"  {info.name}  shape={shape_str}  columns=[{cols}]")
        return "\n".join(lines)

    async def _help(self, args: str, ctx: SessionContext) -> str:
        return (
            "Built-in commands:\n"
            "  /vars              - list DataFrame variable registry\n"
            "  /connect <name>    - switch active data connection\n"
            "  /schema [table]    - view connected database schema\n"
            "  /history           - show session message history\n"
            "  /export            - summarize exportable session artifacts\n"
            "  /schedule          - list scheduled reports\n"
            "  /stats             - show session usage statistics\n"
            "  /advisor [off|model] - show or change advisor status\n"
            "  /voice [on|off|lang <code>] - show or change voice status\n"
            "  /help              - show this help\n"
        )

    async def _connect(self, args: str, ctx: SessionContext) -> str:
        name = args.strip()
        if not name:
            connections = list(ctx.settings.get("connections", {}).keys())
            return f"Available connections: {connections}\nUsage: /connect <name>"
        connections = ctx.settings.get("connections", {})
        if name not in connections:
            return f"Connection '{name}' not found. Available: {list(connections)}"
        self._pool.add_from_config(name, connections[name])
        ctx.settings["_active_connection"] = name
        return f"Connected to '{name}'"

    async def _schema(self, args: str, ctx: SessionContext) -> str:
        active = ctx.settings.get("_active_connection", "default")
        return f"Run: sql_query with schema_inspect for connection '{active}'"

    async def _history(self, args: str, ctx: SessionContext) -> str:
        return (
            f"Session ID: {ctx.session_id}\n"
            f"Transcript: {ctx.transcript_path or '(no transcript)'}\n"
            f"Turns in memory: {len(ctx.messages)}"
        )

    async def _export(self, args: str, ctx: SessionContext) -> str:
        exports = {
            "variables": [info.name for info in ctx.vars.list()],
            "scheduled_reports": len(ctx.settings.get("_scheduled_reports", [])),
            "transcript": ctx.transcript_path or None,
        }
        return f"Exportable session artifacts:\n{json.dumps(exports, ensure_ascii=False, indent=2)}"

    async def _schedule(self, args: str, ctx: SessionContext) -> str:
        schedules = ctx.settings.get("_scheduled_reports", [])
        if not schedules:
            return "No scheduled reports registered in this session."
        lines = ["Scheduled reports:"]
        for entry in schedules:
            lines.append(
                f"  {entry.get('report_name', '(unnamed)')}  cron={entry.get('cron', '')}  format={entry.get('format', '')}"
            )
        return "\n".join(lines)

    async def _stats(self, args: str, ctx: SessionContext) -> str:
        return ctx.stats.format_session_report()

    async def _advisor(self, args: str, ctx: SessionContext) -> str:
        advisor = ctx.settings.setdefault("advisor", {"enabled": False, "model": "haiku"})
        raw = args.strip()
        if not raw:
            status = "enabled" if advisor.get("enabled") else "disabled"
            return f"Advisor is {status} (model={advisor.get('model', 'haiku')})."
        if raw.lower() == "off":
            advisor["enabled"] = False
            return "Advisor disabled."
        advisor["enabled"] = True
        advisor["model"] = raw
        return f"Advisor enabled with model '{raw}'."

    async def _voice(self, args: str, ctx: SessionContext) -> str:
        voice = ctx.settings.setdefault("voice", {"enabled": False, "language": "zh"})
        raw = args.strip()
        if not raw:
            status = "enabled" if voice.get("enabled") else "disabled"
            return f"Voice is {status} (language={voice.get('language', 'zh')})."
        parts = raw.split()
        if parts[0].lower() == "on":
            voice["enabled"] = True
            return f"Voice enabled (language={voice.get('language', 'zh')})."
        if parts[0].lower() == "off":
            voice["enabled"] = False
            return "Voice disabled."
        if parts[0].lower() == "lang" and len(parts) > 1:
            voice["language"] = parts[1]
            return f"Voice language set to '{parts[1]}'."
        return "Usage: /voice [on|off|lang <code>]"
