from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yigthinker.plugins.command import SlashCommand, load_commands_from_dir


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    plugin_dir: Path
    hooks_config: Path | None = None
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    agents_dir: Path | None = None


class PluginLoader:
    """Discovers Yigthinker plugins and loads their components."""

    def __init__(self, plugin_dirs: list[Path] | None = None) -> None:
        self._dirs = plugin_dirs or [
            Path.home() / ".yigthinker" / "plugins",
            Path.cwd() / ".yigthinker" / "plugins",
        ]

    def discover(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for search_dir in self._dirs:
            if not search_dir.exists():
                continue
            for candidate in search_dir.iterdir():
                manifest_path = candidate / ".yigthinker-plugin" / "plugin.json"
                if not manifest_path.exists():
                    continue
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue

                hooks_config: Path | None = None
                if hooks_rel := data.get("hooks"):
                    hooks_path = candidate / hooks_rel
                    if hooks_path.exists():
                        hooks_config = hooks_path

                agents_dir: Path | None = None
                if agents_rel := data.get("agents"):
                    agents_path = candidate / agents_rel
                    if agents_path.is_dir():
                        agents_dir = agents_path

                manifests.append(
                    PluginManifest(
                        name=data.get("name", candidate.name),
                        version=data.get("version", "0.0.0"),
                        description=data.get("description", ""),
                        author=data.get("author", ""),
                        plugin_dir=candidate,
                        hooks_config=hooks_config,
                        mcp_servers=data.get("mcpServers", {}),
                        agents_dir=agents_dir,
                    )
                )
        return manifests

    def load_commands(self) -> list[SlashCommand]:
        commands: list[SlashCommand] = []
        for manifest in self.discover():
            commands_dir = manifest.plugin_dir / "commands"
            if commands_dir.exists():
                commands.extend(load_commands_from_dir(commands_dir))
        return commands

    def load_hooks(self) -> list[tuple[str, str, Any]]:
        """Return (event_type, matcher, CommandHook) tuples from all plugins."""
        from yigthinker.plugins.hook_command import CommandHook

        hooks: list[tuple[str, str, Any]] = []
        for manifest in self.discover():
            if manifest.hooks_config is None:
                continue
            try:
                data = json.loads(manifest.hooks_config.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for event_type, entries in data.items():
                for entry in entries:
                    command = entry.get("command", "")
                    matcher = entry.get("matcher", "*")
                    enabled = entry.get("enabled", True)
                    if command and enabled:
                        hooks.append((event_type, matcher, CommandHook(command)))
        return hooks

    def load_mcp_configs(self) -> dict[str, Any]:
        """Return merged mcpServers dict from all plugins."""
        merged: dict[str, Any] = {}
        for manifest in self.discover():
            merged.update(manifest.mcp_servers)
        return merged

    def load_agent_dirs(self) -> list[Path]:
        """Return paths to agents/ directories contributed by plugins."""
        return [m.agents_dir for m in self.discover() if m.agents_dir is not None]
